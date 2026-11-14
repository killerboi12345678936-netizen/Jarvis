import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

class Settings:
    default_provider = os.getenv("DEFAULT_PROVIDER", "ollama").lower()
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
    gemini_api_key = os.getenv("GEMINI_API_KEY", "")
    nvidia_api_key = os.getenv("NVIDIA_API_KEY", "")
    nvidia_base_url = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1").rstrip("/")
    history_limit = int(os.getenv("HISTORY_LIMIT", "20"))
    system_prompt = os.getenv("JARVIS_SYSTEM_PROMPT", "You are Jarvis, a helpful, honest personal AI assistant.")
    models = {
        "ollama": os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
        "gemini": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        "nvidia": os.getenv("NVIDIA_MODEL", "openai/gpt-oss-20b"),
    }

settings = Settings()
