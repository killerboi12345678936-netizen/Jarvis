from backend.api.routes import sessions, memories
from contextlib import asynccontextmanager
from backend.api.routes import chat, providers
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from backend.api.routes import actions
from backend.api.routes import voice

from backend.core.config import settings
from backend.memory.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    print("Jarvis database initialized.")

    if settings.whisper_preload:
        from backend.voice.speech_to_text import preload_model

        await run_in_threadpool(preload_model)
        print("Whisper model preloaded.")

    yield
    print("Jarvis server shutting down.")


app = FastAPI(
    title="Jarvis AI",
    description="Personal AI assistant API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(providers.router)
app.include_router(sessions.router)
app.include_router(memories.router)
app.include_router(actions.router)
app.include_router(voice.router)


@app.get("/")
async def root():
    return {
        "name": "Jarvis",
        "version": "1.0.0",
        "status": "online",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "jarvis-backend",
    }
