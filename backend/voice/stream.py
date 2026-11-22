
import asyncio
import json
import logging
from collections import deque

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from backend.api.routes.chat import ChatRequest, prepare_chat
from backend.core.config import settings
from backend.memory.database import save_message
from backend.providers.manager import provider_manager, ProviderError
from backend.tools.parser import ToolStreamFilter
from backend.tools.service import process_tool_calls
from backend.voice.sentences import extract_complete_sentences
from backend.voice.speech_to_text import transcribe_samples
from backend.voice.text_to_speech import synthesize_sentence


router = APIRouter(prefix="/api/voice", tags=["Voice Stream"])

logger = logging.getLogger(__name__)

AUDIO_FRAME_BYTES = 4096

PRE_ROLL_MS = 300

BARGE_IN_FRAMES = 2

INTERRUPT = b"__interrupt__"


class VoiceSession:
    def __init__(self):
        self.session_id = None

        self.sample_rate = settings.voice_sample_rate
        self.continuous = True
        self.speech_threshold = settings.vad_speech_threshold
        self.silence_ms = settings.vad_silence_ms
        self.min_speech_ms = settings.vad_min_speech_ms
        self.barge_in_threshold = settings.vad_barge_in_threshold

        self.state = "idle"

        self.pre_roll = deque()
        self.pre_roll_samples = 0

        self.utterance = bytearray()
        self.utterance_samples = 0
        self.speech_samples = 0
        self.last_voice_samples = 0
        self.total_samples = 0

        self.barge_in_count = 0

        self.cancel_event = asyncio.Event()

    def reset_capture(self):
        self.utterance = bytearray()
        self.utterance_samples = 0
        self.speech_samples = 0
        self.last_voice_samples = self.total_samples
        self.barge_in_count = 0

    def rms(self, chunk):
        samples = np.frombuffer(chunk, dtype=np.int16)

        if samples.size == 0:
            return 0.0

        return float(np.sqrt(np.mean(
            samples.astype(np.float32) ** 2
        )) / 32768.0)

    def samples_for_ms(self, ms):
        return int(self.sample_rate * ms / 1000)

    def process_audio(self, chunk):
        """Feed one PCM frame through the VAD state machine.

        Returns PCM bytes when an utterance completes, the sentinel
        INTERRUPT when barge-in speech is detected, or None.
        """

        rms = self.rms(chunk)
        chunk_samples = len(chunk) // 2
        self.total_samples += chunk_samples

        now = self.total_samples

        if self.state in ("listening", "idle"):
            if rms >= self.speech_threshold:
                self.utterance = bytearray()

                for pre_chunk in self.pre_roll:
                    self.utterance.extend(pre_chunk)

                self.utterance.extend(chunk)

                self.utterance_samples = (
                    self.pre_roll_samples + chunk_samples
                )
                self.speech_samples = chunk_samples
                self.last_voice_samples = now
                self.state = "recording"
            else:
                self.pre_roll.append(chunk)
                self.pre_roll_samples += chunk_samples

                max_pre_roll = self.samples_for_ms(PRE_ROLL_MS)

                while (
                    self.pre_roll_samples > max_pre_roll
                    and self.pre_roll
                ):
                    dropped = self.pre_roll.popleft()
                    self.pre_roll_samples -= len(dropped) // 2

        elif self.state == "recording":
            self.utterance.extend(chunk)
            self.utterance_samples += chunk_samples

            if rms >= self.speech_threshold:
                self.speech_samples += chunk_samples
                self.last_voice_samples = now

            silence = now - self.last_voice_samples

            if silence >= self.samples_for_ms(self.silence_ms):
                if self.speech_samples >= self.samples_for_ms(
                    self.min_speech_ms,
                ):
                    utterance = bytes(self.utterance)

                    self.reset_capture()
                    self.pre_roll.clear()
                    self.pre_roll_samples = 0
                    self.state = "transcribing"

                    return utterance

                self.reset_capture()
                self.pre_roll.clear()
                self.pre_roll_samples = 0
                self.state = (
                    "listening" if self.continuous else "idle"
                )

        elif self.state in ("thinking", "speaking"):
            if rms >= self.barge_in_threshold:
                self.barge_in_count += 1

                if self.barge_in_count >= BARGE_IN_FRAMES:
                    self.barge_in_count = 0
                    return INTERRUPT
            else:
                self.barge_in_count = 0

        return None


async def _run_pipeline(websocket, send_json, session, pcm_bytes):
    cancel = session.cancel_event

    try:
        await send_json({"type": "state", "state": "transcribing"})

        result = await run_in_threadpool(
            transcribe_samples,
            bytes(pcm_bytes),
        )

        text = result.get("text", "").strip()

        await send_json({
            "type": "transcript",
            "text": text,
            "language": result.get("language"),
        })

        if not text:
            return

        try:
            chat_request = ChatRequest(
                message=text,
                session_id=session.session_id,
            )

            session_id, provider, model, messages = await prepare_chat(
                chat_request,
            )

            session.session_id = session_id

        except Exception:
            session.session_id = None

            chat_request = ChatRequest(message=text)

            session_id, provider, model, messages = await prepare_chat(
                chat_request,
            )

            session.session_id = session_id

        await send_json({
            "type": "response_start",
            "session_id": session_id,
            "provider": provider,
            "model": model,
        })

        await send_json({"type": "state", "state": "thinking"})

        # The VAD only processes barge-in frames while it believes
        # Jarvis is busy, so the server-side state must mirror the
        # events sent to the client.
        session.state = "thinking"

        full_response = ""
        pending_actions = []
        round_messages = list(messages)
        sentence_index = 0
        started_speaking = False
        pending_text = ""

        rounds = max(1, settings.tool_max_rounds)
        interrupted = False

        async def flush_pending_text():
            nonlocal pending_text, sentence_index, started_speaking

            leftover = pending_text.strip()

            pending_text = ""

            if not leftover:
                return

            if session.cancel_event.is_set():
                return

            if not started_speaking:
                await send_json({
                    "type": "state",
                    "state": "speaking",
                })

                session.state = "speaking"
                started_speaking = True

            await _speak_sentence(
                websocket,
                send_json,
                session,
                leftover,
                sentence_index,
            )

            sentence_index += 1

        for _ in range(rounds):
            stream_filter = ToolStreamFilter()
            round_text = ""

            async for chunk in provider_manager.stream(
                messages=round_messages,
                provider=provider,
                model=model,
            ):
                if session.cancel_event.is_set():
                    interrupted = True
                    break

                if not chunk:
                    continue

                round_text += chunk

                visible = stream_filter.feed(chunk)

                if visible:
                    full_response += visible
                    pending_text += visible

                    sentences, pending_text = (
                        extract_complete_sentences(pending_text)
                    )

                    for sentence in sentences:
                        if session.cancel_event.is_set():
                            interrupted = True
                            break

                        if not started_speaking:
                            started_speaking = True
                            await send_json({
                                "type": "state",
                                "state": "speaking",
                            })
                            session.state = "speaking"

                        await _speak_sentence(
                            websocket,
                            send_json,
                            session,
                            sentence,
                            sentence_index,
                        )
                        sentence_index += 1

            if interrupted:
                break

            tail = stream_filter.finish()

            if tail:
                full_response += tail
                pending_text += tail

                sentences, pending_text = (
                    extract_complete_sentences(pending_text)
                )

                for sentence in sentences:
                    if session.cancel_event.is_set():
                        interrupted = True
                        break

                    if not started_speaking:
                        await send_json({
                            "type": "state",
                            "state": "speaking",
                        })
                        session.state = "speaking"
                        started_speaking = True

                    await _speak_sentence(
                        websocket,
                        send_json,
                        session,
                        sentence,
                        sentence_index,
                    )
                    sentence_index += 1

            if interrupted:
                break

            if not stream_filter.tool_calls:
                break

            follow_up_parts, actions, _results = (
                await process_tool_calls(stream_filter.tool_calls)
            )

            pending_actions.extend(actions)

            if pending_actions:
                await flush_pending_text()

                note = (
                    "I have proposed an action that needs your "
                    "approval in the actions panel."
                )

                if not started_speaking:
                    await send_json({"type": "state", "state": "speaking"})
                    session.state = "speaking"
                    started_speaking = True

                await _speak_sentence(
                    websocket,
                    send_json,
                    session,
                    note,
                    sentence_index,
                )
                sentence_index += 1

                break

            if not follow_up_parts:
                break

            round_messages.append({
                "role": "assistant",
                "content": round_text,
            })

            round_messages.append({
                "role": "user",
                "content": (
                    "\n".join(follow_up_parts)
                    + "\nUse the results above to continue your answer."
                ),
            })

        await flush_pending_text()

        cleaned_response = full_response.strip()

        if cleaned_response:
            await save_message(
                session_id,
                "assistant",
                provider,
                cleaned_response,
            )

        if cancel.is_set():
            await send_json({"type": "interrupted"})

        await send_json({
            "type": "response_done",
            "response": cleaned_response,
            "interrupted": cancel.is_set(),
        })

    except ProviderError as error:
        logger.warning("Voice pipeline provider error: %s", error)

        await send_json({
            "type": "error",
            "message": str(error),
        })

    except Exception as error:
        logger.exception("Voice pipeline error")

        await send_json({
            "type": "error",
            "message": f"Voice processing failed: {error}",
        })

    finally:
        if session.state not in ("listening", "idle"):
            session.state = (
                "listening" if session.continuous else "idle"
            )

            await send_json({
                "type": "state",
                "state": session.state,
            })


async def _speak_sentence(websocket, send_json, session, sentence, index):
    clean = sentence.strip()

    if not clean:
        return

    await send_json({
        "type": "sentence_start",
        "index": index,
        "text": clean,
    })

    audio_path = await synthesize_sentence(clean[:1000])

    audio_data = audio_path.read_bytes()

    async with session.send_lock:
        await websocket.send_json({
            "type": "audio_start",
            "index": index,
            "size": len(audio_data),
            "mime": "audio/wav",
        })

        for offset in range(0, len(audio_data), AUDIO_FRAME_BYTES):
            await websocket.send_bytes(
                audio_data[offset:offset + AUDIO_FRAME_BYTES],
            )

        await websocket.send_json({
            "type": "audio_end",
            "index": index,
        })

    audio_path.unlink(missing_ok=True)


@router.websocket("/ws")
async def voice_ws(websocket: WebSocket):
    await websocket.accept()

    session = VoiceSession()
    session.send_lock = asyncio.Lock()

    generation_task = None

    async def send_json(payload):
        async with session.send_lock:
            await websocket.send_json(payload)

    async def trigger_interrupt():
        if generation_task and not generation_task.done():
            session.cancel_event.set()

            await send_json({
                "type": "interrupt_ack",
            })

    async def start_generation(pcm_bytes):
        nonlocal generation_task

        session.cancel_event = asyncio.Event()
        session.state = "transcribing"
        session.pre_roll.clear()
        session.pre_roll_samples = 0

        generation_task = asyncio.create_task(
            _run_pipeline(websocket, send_json, session, pcm_bytes),
        )

    def handle_control(data):
        nonlocal generation_task

        message_type = data.get("type")

        if message_type == "config":
            if "sample_rate" in data:
                session.sample_rate = int(data["sample_rate"])

            if "continuous" in data:
                session.continuous = bool(data["continuous"])

            if "speech_threshold" in data:
                session.speech_threshold = float(
                    data["speech_threshold"],
                )

            if "silence_ms" in data:
                session.silence_ms = int(data["silence_ms"])

            if "min_speech_ms" in data:
                session.min_speech_ms = int(data["min_speech_ms"])

            if "barge_in_threshold" in data:
                session.barge_in_threshold = float(
                    data["barge_in_threshold"],
                )

            return {"type": "config_ack"}

        if message_type == "listen":
            session.state = "listening"

            return {"type": "state", "state": "listening"}

        if message_type == "interrupt":
            if generation_task and not generation_task.done():
                session.cancel_event.set()

            return {"type": "interrupt_ack"}

        if message_type == "stop":
            if generation_task and not generation_task.done():
                session.cancel_event.set()

            session.state = "idle"

            return {"type": "state", "state": "idle"}

        if message_type == "ping":
            return {"type": "pong"}

        return None

    try:
        while True:
            message = await websocket.receive()

            if message.get("type") == "websocket.disconnect":
                break

            if message.get("bytes"):
                result = session.process_audio(message["bytes"])

                if result == INTERRUPT:
                    await trigger_interrupt()
                elif result is not None:
                    await start_generation(result)

            elif message.get("text"):
                try:
                    data = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue

                reply = handle_control(data)

                if reply:
                    await send_json(reply)

                if data.get("type") == "stop":
                    break

    except WebSocketDisconnect:
        pass

    except Exception:
        logger.exception("Voice websocket error")

    finally:
        if generation_task:
            session.cancel_event.set()

            try:
                await asyncio.wait_for(generation_task, timeout=10)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                generation_task.cancel()

        try:
            await websocket.close()
        except Exception:
            pass
