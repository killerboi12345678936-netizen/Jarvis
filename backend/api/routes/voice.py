
import logging

from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from backend.voice.speech_to_text import transcribe_audio
from backend.voice.text_to_speech import (
    synthesize_speech,
    synthesize_sentence,
)


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

router = APIRouter(prefix="/api/voice", tags=["Voice"])

logger = logging.getLogger(__name__)

MAX_AUDIO_SIZE = 20 * 1024 * 1024

ALLOWED_AUDIO_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".ogg",
    ".webm",
}


# --------------------------------------------------
# REQUEST SCHEMAS
# --------------------------------------------------

class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


class SentenceSpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


# --------------------------------------------------
# SPEECH TO TEXT
# --------------------------------------------------

@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):

    suffix = Path(file.filename or "").suffix.lower()

    if suffix not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported audio format.",
        )

    try:
        audio_data = await file.read(MAX_AUDIO_SIZE + 1)

        if not audio_data:
            raise HTTPException(
                status_code=400,
                detail="Uploaded audio file is empty.",
            )

        if len(audio_data) > MAX_AUDIO_SIZE:
            raise HTTPException(
                status_code=413,
                detail="Audio file exceeds the 20 MB limit.",
            )

        result = await run_in_threadpool(
            transcribe_audio,
            audio_data,
            suffix,
        )

        return result

    except HTTPException:
        raise

    except Exception as exc:
        logger.exception("JARVIS STT ERROR")

        raise HTTPException(
            status_code=500,
            detail=f"Speech recognition failed: {exc}",
        ) from exc

    finally:
        await file.close()


# --------------------------------------------------
# AUDIO RESPONSE HELPER
# --------------------------------------------------

def audio_file_response(audio_path: Path):
    audio_path = Path(audio_path)

    if not audio_path.is_file():
        raise RuntimeError(
            "TTS completed but the audio file does not exist."
        )

    if audio_path.stat().st_size == 0:
        raise RuntimeError(
            "TTS generated an empty audio file."
        )

    return FileResponse(
        path=str(audio_path),
        media_type="audio/wav",
        filename="jarvis_speech.wav",
        background=BackgroundTask(
            audio_path.unlink,
            missing_ok=True,
        ),
    )


# --------------------------------------------------
# TEXT TO SPEECH
# --------------------------------------------------

@router.post("/speak")
async def speak(request: SpeechRequest):

    audio_path = None

    try:
        audio_path = await synthesize_speech(request.text)

        return audio_file_response(audio_path)

    except Exception as exc:
        logger.exception("JARVIS TTS ERROR")

        if audio_path is not None:
            try:
                Path(audio_path).unlink(missing_ok=True)
            except OSError:
                logger.exception("Could not clean up failed TTS file")

        error_message = str(exc).strip() or (
            f"{type(exc).__name__}: An error occurred."
        )

        raise HTTPException(
            status_code=503,
            detail=error_message,
        ) from exc


# --------------------------------------------------
# SENTENCE-LEVEL TEXT TO SPEECH
# --------------------------------------------------

@router.post("/speak/sentence")
async def speak_sentence(request: SentenceSpeechRequest):

    audio_path = None

    try:
        audio_path = await synthesize_sentence(request.text)

        return audio_file_response(audio_path)

    except Exception as exc:
        logger.exception("JARVIS SENTENCE TTS ERROR")

        if audio_path is not None:
            try:
                Path(audio_path).unlink(missing_ok=True)
            except OSError:
                logger.exception(
                    "Could not clean up failed sentence audio"
                )

        error_message = str(exc).strip() or (
            f"{type(exc).__name__}: An error occurred."
        )

        raise HTTPException(
            status_code=503,
            detail=error_message,
        ) from exc
