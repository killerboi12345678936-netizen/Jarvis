
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.config import settings
from backend.providers.manager import (
    provider_manager,
    ProviderError,
)

router = APIRouter(prefix="/api/providers", tags=["Providers"])


class ProviderSelection(BaseModel):
    provider: str
    model: str | None = Field(default=None, max_length=200)


@router.get("/")
async def list_providers():
    return {
        "default_provider": provider_manager.default_provider,
        "providers": await provider_manager.available_providers(),
    }


@router.get("/ollama/models")
async def list_ollama_models():
    try:
        return {"models": await provider_manager.list_ollama_models()}
    except ProviderError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/validate")
async def validate_provider(selection: ProviderSelection):
    provider = selection.provider.lower()

    try:
        model = selection.model or provider_manager.get_model(provider)

        if provider == "ollama":
            models = await provider_manager.list_ollama_models()

            if model not in models:
                raise HTTPException(
                    status_code=400,
                    detail=f"Model '{model}' is not installed in Ollama.",
                )

        if provider == "gemini" and not settings.gemini_api_key:
            raise HTTPException(
                status_code=400, detail="Gemini API key missing.")

        if provider == "nvidia" and not settings.nvidia_api_key:
            raise HTTPException(
                status_code=400, detail="NVIDIA API key missing.")

        return {
            "valid": True,
            "provider": provider,
            "model": model,
        }

    except ProviderError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
