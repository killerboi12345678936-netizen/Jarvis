
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
from backend.providers.manager import (
    provider_manager,
    ProviderError,
)
from backend.tools.parser import ToolStreamFilter, build_tool_prompt
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

        full_response = ""
        pending_actions = []
        tool_results = []

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

        if full_response.strip():
            await save_message(
                session_id,
                "assistant",
                provider,
                full_response.strip(),
            )

        return ChatResponse(
            session_id=session_id,
            provider=provider,
            model=model,
            response=full_response.strip(),
        )

    except ProviderError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error


def _tool_action_note(pending_actions):
    if not pending_actions:
        return ""

    names = ", ".join(
        action["tool"] for action in pending_actions
    )

    return (
        f"\n\n[Action proposed: {names} - "
        "approve or reject it in the Actions panel.]"
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
            round_messages = list(messages)

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

            cleaned = full_response.strip()

            if cleaned:
                await save_message(
                    session_id,
                    "assistant",
                    provider,
                    cleaned,
                )

            yield stream_event(
                "done",
                session_id=session_id,
                provider=provider,
                model=model,
                response=cleaned + _tool_action_note(pending_actions),
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
