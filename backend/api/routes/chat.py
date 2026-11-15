
import json
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
from backend.providers.manager import (
    provider_manager,
    ProviderError,
)

router = APIRouter(prefix="/api/chat", tags=["Chat"])


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

    messages = [
        {
            "role": "system",
            "content": settings.system_prompt,
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

        answer = await provider_manager.ask(
            messages=messages,
            provider=provider,
            model=model,
        )

        await save_message(
            session_id,
            "assistant",
            provider,
            answer,
        )

        return ChatResponse(
            session_id=session_id,
            provider=provider,
            model=model,
            response=answer,
        )

    except ProviderError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error


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

        yield stream_event(
            "start",
            session_id=session_id,
            provider=provider,
            model=model,
        )

        try:
            async for chunk in provider_manager.stream(
                messages=messages,
                provider=provider,
                model=model,
            ):
                if not chunk:
                    continue

                full_response += chunk

                yield stream_event(
                    "chunk",
                    text=chunk,
                )

            if full_response:
                await save_message(
                    session_id,
                    "assistant",
                    provider,
                    full_response,
                )

            yield stream_event(
                "done",
                session_id=session_id,
                provider=provider,
                model=model,
                response=full_response,
            )

        except ProviderError as error:
            yield stream_event(
                "error",
                message=str(error),
            )

        except Exception:
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
