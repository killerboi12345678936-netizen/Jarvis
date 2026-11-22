
import json
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.core.config import settings
from backend.memory.database import (
    create_session,
    get_session,
    get_messages,
    save_message,
)
from backend.memory.retrieval import (
    find_relevant_memories,
    memory_context_block,
)
from backend.integrations.telegram.report import (
    build_study_report_safe,
    match_study_intent,
)
from backend.providers.manager import (
    provider_manager,
    ProviderError,
)
from backend.tools.parser import (
    ToolStreamFilter,
    build_tool_prompt,
    FAKE_PROPOSAL_RE,
    MALFORMED_CALL_CORRECTION,
    TOOL_CALL_CORRECTION,
    normalize_visible_text,
    strip_fake_proposals,
)
from backend.tools.service import process_tool_calls

router = APIRouter(prefix="/api/chat", tags=["Chat"])

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    session_id: int | None = None
    provider: Literal["ollama", "gemini", "nvidia"] | None = None
    model: str | None = Field(default=None, max_length=200)


class ChatResponse(BaseModel):
    session_id: int
    provider: str
    model: str
    response: str


async def prepare_chat(request: ChatRequest):
    provider = (
        request.provider or provider_manager.default_provider
    ).lower()

    model = request.model or provider_manager.get_model(provider)

    if request.session_id is None:
        session_id = await create_session()
    else:
        session = await get_session(request.session_id)

        if not session:
            raise HTTPException(
                status_code=404,
                detail="Conversation session not found.",
            )

        if session["closed_at"]:
            raise HTTPException(
                status_code=400,
                detail="This conversation is closed. Start a new session.",
            )

        session_id = request.session_id

    await save_message(
        session_id,
        "user",
        provider,
        request.message,
    )

    history = await get_messages(
        session_id,
        limit=settings.history_limit,
    )

    system_prompt = settings.system_prompt

    memories = await find_relevant_memories(
        request.message,
        limit=settings.memory_context_limit,
    )

    memory_block = memory_context_block(memories)

    if memory_block:
        system_prompt = f"{system_prompt}\n\n{memory_block}"

    if settings.tools_enabled:
        system_prompt = (
            f"{system_prompt}\n\n{build_tool_prompt()}"
        )

    messages = [
        {
            "role": "system",
            "content": system_prompt,
        }
    ]

    messages.extend([
        {
            "role": item["role"],
            "content": item["content"],
        }
        for item in history
        if item["role"] in ("user", "assistant")
    ])

    return session_id, provider, model, messages


def stream_event(event_type: str, **data):
    payload = {
        "type": event_type,
        **data,
    }

    return f"data: {json.dumps(payload)}\n\n"


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        session_id, provider, model, messages = await prepare_chat(
            request
        )

        # Deterministic route: study-group requests go straight to the
        # Telegram digest/plan workflow instead of hoping the model
        # picks a tool.
        if match_study_intent(request.message):
            report = await build_study_report_safe()

            await save_message(
                session_id,
                "assistant",
                provider,
                report,
            )

            return ChatResponse(
                session_id=session_id,
                provider=provider,
                model=model,
                response=report,
            )

        full_response = ""
        pending_actions = []
        tool_results = []
        corrected = False
        corrected_malformed = False

        round_messages = list(messages)

        for _ in range(max(1, settings.tool_max_rounds)):
            answer = await provider_manager.ask(
                messages=round_messages,
                provider=provider,
                model=model,
            )

            stream_filter = ToolStreamFilter()
            visible = stream_filter.feed(answer) + stream_filter.finish()

            full_response += visible

            if not stream_filter.tool_calls:
                # The model may fake a proposal note instead of
                # emitting a tool call; give it one explicit retry.
                if not corrected and FAKE_PROPOSAL_RE.search(visible):
                    corrected = True
                    round_messages.append({
                        "role": "assistant",
                        "content": answer,
                    })
                    round_messages.append({
                        "role": "user",
                        "content": TOOL_CALL_CORRECTION,
                    })
                    continue

                # The model tried to call a tool but the markup was
                # unparseable; give it one explicit retry rather than
                # ending the turn with nothing.
                if not corrected_malformed and stream_filter.invalid_blocks:
                    corrected_malformed = True
                    round_messages.append({
                        "role": "assistant",
                        "content": answer,
                    })
                    round_messages.append({
                        "role": "user",
                        "content": MALFORMED_CALL_CORRECTION,
                    })
                    continue

                break

            follow_up_parts = []

            parts, actions, results = await process_tool_calls(
                stream_filter.tool_calls,
            )

            follow_up_parts.extend(parts)
            pending_actions.extend(actions)
            tool_results.extend(results)

            if pending_actions or not follow_up_parts:
                break

            round_messages.append({
                "role": "assistant",
                "content": answer,
            })

            round_messages.append({
                "role": "user",
                "content": (
                    "\n".join(follow_up_parts)
                    + "\nUse the results above to continue your answer."
                ),
            })

        had_fake = bool(FAKE_PROPOSAL_RE.search(full_response))
        cleaned = strip_fake_proposals(
            normalize_visible_text(full_response)
        ).strip()
        note = _tool_action_note(pending_actions)

        if corrected and had_fake and not note:
            cleaned = (
                cleaned
                + "\n\n(I could not prepare that action just now. "
                "Please try again.)"
            ).strip()

        if corrected_malformed and not cleaned and not note:
            cleaned = (
                "(I could not prepare that action just now. "
                "Please try again.)"
            )

        if cleaned or note:
            await save_message(
                session_id,
                "assistant",
                provider,
                (cleaned + note).strip(),
            )

        return ChatResponse(
            session_id=session_id,
            provider=provider,
            model=model,
            response=(cleaned + note).strip(),
        )

    except ProviderError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error


def _describe_action(action):
    tool = action["tool"]
    arguments = action["arguments"]

    if tool == "create_note":
        return (
            f"create_note: file '{arguments.get('filename', '?')}' "
            f"with content: {str(arguments.get('content', ''))[:200]}"
        )

    if tool == "open_application":
        return f"open_application: {arguments.get('name', '?')}"

    if tool == "create_event":
        return (
            f"create_event: '{arguments.get('title', '?')}' "
            f"from {arguments.get('start', '?')} "
            f"to {arguments.get('end', '?')}"
        )

    if tool == "delete_event":
        return f"delete_event: event_id {arguments.get('event_id', '?')}"

    try:
        return f"{tool}: {json.dumps(arguments)[:200]}"
    except (TypeError, ValueError):
        return tool


def _tool_action_note(pending_actions):
    if not pending_actions:
        return ""

    lines = [
        _describe_action(action) for action in pending_actions
    ]

    return (
        "\n\n[Action proposed and awaiting your approval - "
        + "; ".join(lines)
        + ". Open the Actions panel (or use the buttons below) to "
        "approve or reject.]"
    )


@router.post("/stream")
async def chat_stream(request: ChatRequest):
    try:
        session_id, provider, model, messages = await prepare_chat(
            request
        )
    except HTTPException:
        raise
    except ProviderError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error

    async def generate():
        full_response = ""
        pending_actions = []
        tool_results = []

        yield stream_event(
            "start",
            session_id=session_id,
            provider=provider,
            model=model,
        )

        try:
            # Deterministic route: study-group requests go straight to
            # the Telegram digest/plan workflow instead of hoping the
            # model picks a tool.
            if match_study_intent(request.message):
                report = await build_study_report_safe()

                await save_message(
                    session_id,
                    "assistant",
                    provider,
                    report,
                )

                yield stream_event("chunk", text=report)

                yield stream_event(
                    "done",
                    session_id=session_id,
                    provider=provider,
                    model=model,
                    response=report,
                    pending_actions=[],
                    tool_results=[],
                )

                return

            round_messages = list(messages)
            corrected = False
            corrected_malformed = False

            for _ in range(max(1, settings.tool_max_rounds)):
                stream_filter = ToolStreamFilter()
                round_text = ""

                async for chunk in provider_manager.stream(
                    messages=round_messages,
                    provider=provider,
                    model=model,
                ):
                    if not chunk:
                        continue

                    round_text += chunk

                    visible = stream_filter.feed(chunk)

                    if visible:
                        full_response += visible

                        yield stream_event(
                            "chunk",
                            text=visible,
                        )

                tail = stream_filter.finish()

                if tail:
                    full_response += tail

                    yield stream_event(
                        "chunk",
                        text=tail,
                    )

                if not stream_filter.tool_calls:
                    # The model may fake a proposal note instead of
                    # emitting a tool call; give it one explicit
                    # retry before giving up.
                    if (
                        not corrected
                        and FAKE_PROPOSAL_RE.search(round_text)
                    ):
                        corrected = True
                        round_messages.append({
                            "role": "assistant",
                            "content": round_text,
                        })
                        round_messages.append({
                            "role": "user",
                            "content": TOOL_CALL_CORRECTION,
                        })
                        continue

                    # Unparseable tool-call markup: one corrective
                    # round, then the honest fallback below.
                    if (
                        not corrected_malformed
                        and stream_filter.invalid_blocks
                    ):
                        corrected_malformed = True
                        round_messages.append({
                            "role": "assistant",
                            "content": round_text,
                        })
                        round_messages.append({
                            "role": "user",
                            "content": MALFORMED_CALL_CORRECTION,
                        })
                        continue

                    break

                follow_up_parts, actions, results = (
                    await process_tool_calls(stream_filter.tool_calls)
                )

                pending_actions.extend(actions)
                tool_results.extend(results)

                if pending_actions or not follow_up_parts:
                    break

                round_messages.append({
                    "role": "assistant",
                    "content": round_text,
                })

                round_messages.append({
                    "role": "user",
                    "content": (
                        "\n".join(follow_up_parts)
                        + "\nUse the results above to continue "
                        "your answer."
                    ),
                })

            had_fake = bool(FAKE_PROPOSAL_RE.search(full_response))
            cleaned = strip_fake_proposals(
                normalize_visible_text(full_response)
            ).strip()

            # Persist the proposal so the conversation still shows what
            # was asked for after a reload; without this, a turn that
            # only emitted a tool call would vanish from history.
            note = _tool_action_note(pending_actions)

            if corrected and had_fake and not note:
                cleaned = (
                    cleaned
                    + "\n\n(I could not prepare that action just now. "
                    "Please try again.)"
                ).strip()

            if corrected_malformed and not cleaned and not note:
                cleaned = (
                    "(I could not prepare that action just now. "
                    "Please try again.)"
                )

            if cleaned or note:
                await save_message(
                    session_id,
                    "assistant",
                    provider,
                    (cleaned + note).strip(),
                )

            yield stream_event(
                "done",
                session_id=session_id,
                provider=provider,
                model=model,
                response=cleaned + note,
                pending_actions=pending_actions,
                tool_results=tool_results,
            )

        except ProviderError as error:
            yield stream_event(
                "error",
                message=str(error),
            )

        except Exception:
            logger.exception("Chat stream error")

            yield stream_event(
                "error",
                message="An unexpected error occurred while generating the response.",
            )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
