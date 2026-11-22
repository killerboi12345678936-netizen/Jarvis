from backend.api.routes import sessions, memories
from contextlib import asynccontextmanager
from backend.api.routes import chat, providers
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from backend.api.routes import actions
from backend.api.routes import voice
from backend.api.routes import integrations
from backend.api.routes import auth
from backend.voice.stream import router as voice_stream_router
from backend.security.device_auth import DeviceAuthMiddleware

from backend.core.config import settings
from backend.memory.database import init_db
from backend.tools.permissions import recover_stale_actions


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    print("Jarvis database initialized.")

    recovered = await recover_stale_actions()

    if recovered:
        print(
            f"Recovered {recovered} action(s) that were stuck in "
            "'executing' (backend previously interrupted mid-run)."
        )

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

# Device auth runs inside CORS so that even rejected requests carry
# CORS headers (added later in code = outermost middleware).
app.add_middleware(
    DeviceAuthMiddleware,
    enabled=settings.device_auth_enabled,
)

app.add_middleware(
    CORSMiddleware,
    # Local + private-LAN app: allow any localhost port (dev server,
    # preview, other local tooling), file:// pages (Origin null), and
    # private-network addresses a phone or laptop uses on the home
    # Wi-Fi. Public internet origins are still rejected.
    allow_origins=["null"],
    allow_origin_regex=(
        r"^https?://("
        r"localhost|127\.0\.0\.1|"
        r"192\.168\.\d{1,3}\.\d{1,3}|"
        r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
        r"172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
        r")(:\d+)?$"
    ),
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
app.include_router(voice_stream_router)
app.include_router(integrations.router)
app.include_router(auth.router)


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
