
import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def parse_allowed_apps(raw):
    return {
        pair.split("=", 1)[0].strip().lower(): pair.split("=", 1)[1].strip()
        for pair in raw.split(",")
        if "=" in pair
    }


class Settings:
    app_name = "Jarvis"
    app_version = "1.0.0"

    default_provider = os.getenv("DEFAULT_PROVIDER", "ollama").lower()

    ollama_url = os.getenv(
        "OLLAMA_URL",
        "http://localhost:11434"
    ).rstrip("/")

    gemini_api_key = os.getenv("GEMINI_API_KEY", "")

    nvidia_api_key = os.getenv("NVIDIA_API_KEY", "")

    nvidia_base_url = os.getenv(
        "NVIDIA_BASE_URL",
        "https://integrate.api.nvidia.com/v1"
    ).rstrip("/")

    history_limit = int(os.getenv("HISTORY_LIMIT", "20"))

    system_prompt = os.getenv(
        "JARVIS_SYSTEM_PROMPT",
        "You are Jarvis, a helpful, honest personal AI assistant."
    )

    models = {
        "ollama": os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
        "gemini": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        "nvidia": os.getenv("NVIDIA_MODEL", "openai/gpt-oss-20b"),
    }

    # ---- Memory ----
    memory_context_limit = int(os.getenv("MEMORY_CONTEXT_LIMIT", "6"))

    # ---- Tools ----
    tools_enabled = os.getenv("TOOLS_ENABLED", "1") == "1"
    tool_max_rounds = int(os.getenv("TOOL_MAX_ROUNDS", "2"))

    # ---- Voice ----
    whisper_model = os.getenv("WHISPER_MODEL", "base")
    whisper_device = os.getenv("WHISPER_DEVICE", "cpu")
    whisper_compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
    whisper_preload = os.getenv("WHISPER_PRELOAD", "0") == "1"

    voice_sample_rate = int(os.getenv("VOICE_SAMPLE_RATE", "16000"))

    vad_speech_threshold = float(os.getenv("VAD_SPEECH_THRESHOLD", "0.015"))
    vad_silence_ms = int(os.getenv("VAD_SILENCE_MS", "900"))
    vad_min_speech_ms = int(os.getenv("VAD_MIN_SPEECH_MS", "300"))
    vad_barge_in_threshold = float(
        os.getenv("VAD_BARGE_IN_THRESHOLD", "0.035")
    )

    # ---- Telegram (read-only study groups) ----
    telegram_api_id = os.getenv("TELEGRAM_API_ID", "")
    telegram_api_hash = os.getenv("TELEGRAM_API_HASH", "")
    telegram_session = os.getenv("TELEGRAM_SESSION", "")

    telegram_groups = {
        "mathematics": os.getenv("TELEGRAM_GROUP_MATH", ""),
        "physics": os.getenv("TELEGRAM_GROUP_PHYSICS", ""),
        "chemistry": os.getenv("TELEGRAM_GROUP_CHEMISTRY", ""),
    }

    # ---- Calendar ----
    calendar_ics_url = os.getenv("CALENDAR_ICS_URL", "")
    calendar_ics_file = os.getenv("CALENDAR_ICS_FILE", "")

    # ---- Desktop ----
    desktop_allowed_apps = parse_allowed_apps(
        os.getenv(
            "DESKTOP_ALLOWED_APPS",
            "notepad=notepad,calculator=calc,paint=mspaint",
        )
    )


settings = Settings()
