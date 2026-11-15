
import json
import httpx

from backend.core.config import settings


class ProviderError(RuntimeError):
    pass


class ProviderManager:

    def __init__(self):
        self.default_provider = settings.default_provider

    def get_model(self, provider: str) -> str:
        if provider not in settings.models:
            raise ProviderError(f"Unknown provider: {provider}")
        return settings.models[provider]

    async def available_providers(self):
        results = {}

        for provider in settings.models:
            configured = (
                provider == "ollama"
                or (
                    provider == "gemini"
                    and bool(settings.gemini_api_key)
                )
                or (
                    provider == "nvidia"
                    and bool(settings.nvidia_api_key)
                )
            )

            online = False

            if configured:
                try:
                    if provider == "ollama":
                        async with httpx.AsyncClient(timeout=5) as client:
                            response = await client.get(
                                f"{settings.ollama_url}/api/tags"
                            )
                            response.raise_for_status()
                        online = True
                    else:
                        online = True

                except httpx.HTTPError:
                    online = False

            results[provider] = {
                "configured": configured,
                "online": online,
                "model": settings.models[provider],
            }

        return results

    async def list_ollama_models(self):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{settings.ollama_url}/api/tags"
                )
                response.raise_for_status()

            return [
                model["name"]
                for model in response.json().get("models", [])
            ]

        except httpx.HTTPError as error:
            raise ProviderError(
                f"Could not retrieve Ollama models: {error}"
            ) from error

    # ==========================================
    # NORMAL CHAT
    # ==========================================

    async def ask(self, messages, provider=None, model=None):

        provider = (provider or self.default_provider).lower()
        model = model or self.get_model(provider)

        if provider == "ollama":
            return await self._ask_ollama(messages, model)

        if provider == "gemini":
            return await self._ask_gemini(messages, model)

        if provider == "nvidia":
            return await self._ask_nvidia(messages, model)

        raise ProviderError(f"Unsupported provider: {provider}")

    # ==========================================
    # STREAMING CHAT DISPATCHER
    # ==========================================

    async def stream(self, messages, provider=None, model=None):

        provider = (provider or self.default_provider).lower()
        model = model or self.get_model(provider)

        if provider == "ollama":
            async for chunk in self._stream_ollama(messages, model):
                yield chunk

        elif provider == "gemini":
            async for chunk in self._stream_gemini(messages, model):
                yield chunk

        elif provider == "nvidia":
            async for chunk in self._stream_nvidia(messages, model):
                yield chunk

        else:
            raise ProviderError(f"Unsupported provider: {provider}")

    # ==========================================
    # OLLAMA NORMAL CHAT
    # ==========================================

    async def _ask_ollama(self, messages, model):

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
        }

        try:
            async with httpx.AsyncClient(timeout=180) as client:
                response = await client.post(
                    f"{settings.ollama_url}/api/chat",
                    json=payload,
                )
                response.raise_for_status()

            answer = response.json().get(
                "message", {}
            ).get("content", "")

            if not answer.strip():
                raise ProviderError("Ollama returned an empty response.")

            return answer.strip()

        except httpx.HTTPError as error:
            raise ProviderError(f"Ollama failed: {error}") from error

    # ==========================================
    # OLLAMA STREAMING
    # ==========================================

    async def _stream_ollama(self, messages, model):

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
        }

        try:
            async with httpx.AsyncClient(timeout=180) as client:
                async with client.stream(
                    "POST",
                    f"{settings.ollama_url}/api/chat",
                    json=payload,
                ) as response:

                    response.raise_for_status()

                    async for line in response.aiter_lines():

                        if not line:
                            continue

                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError as error:
                            raise ProviderError(
                                "Ollama returned invalid streaming data."
                            ) from error

                        if event.get("error"):
                            raise ProviderError(
                                f"Ollama failed: {event['error']}"
                            )

                        content = event.get(
                            "message", {}
                        ).get("content", "")

                        if content:
                            yield content

        except httpx.HTTPError as error:
            raise ProviderError(
                f"Ollama streaming failed: {error}"
            ) from error

    # ==========================================
    # GEMINI NORMAL CHAT
    # ==========================================

    async def _ask_gemini(self, messages, model):

        if not settings.gemini_api_key:
            raise ProviderError("Gemini API key is not configured.")

        system = "\n\n".join(
            m["content"] for m in messages if m["role"] == "system"
        )

        contents = []

        for message in messages:

            if message["role"] == "system":
                continue

            if message["role"] not in ("user", "assistant"):
                continue

            contents.append({
                "role": "model" if message["role"] == "assistant" else "user",
                "parts": [{"text": message["content"]}],
            })

        payload = {"contents": contents}

        if system:
            payload["systemInstruction"] = {
                "parts": [{"text": system}]
            }

        try:
            async with httpx.AsyncClient(timeout=180) as client:
                response = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    headers={
                        "x-goog-api-key": settings.gemini_api_key
                    },
                    json=payload,
                )

                response.raise_for_status()

            candidates = response.json().get("candidates", [])

            if not candidates:
                raise ProviderError("Gemini returned no candidates.")

            answer = "".join(
                part.get("text", "")
                for part in candidates[0].get(
                    "content", {}
                ).get("parts", [])
            ).strip()

            if not answer:
                raise ProviderError("Gemini returned an empty response.")

            return answer

        except httpx.HTTPError as error:
            raise ProviderError(f"Gemini failed: {error}") from error

    # ==========================================
    # GEMINI STREAMING
    # ==========================================

    async def _stream_gemini(self, messages, model):

        if not settings.gemini_api_key:
            raise ProviderError("Gemini API key is not configured.")

        system = "\n\n".join(
            m["content"] for m in messages if m["role"] == "system"
        )

        contents = []

        for message in messages:

            if message["role"] == "system":
                continue

            if message["role"] not in ("user", "assistant"):
                continue

            contents.append({
                "role": "model" if message["role"] == "assistant" else "user",
                "parts": [{"text": message["content"]}],
            })

        payload = {"contents": contents}

        if system:
            payload["systemInstruction"] = {
                "parts": [{"text": system}]
            }

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:streamGenerateContent?alt=sse"
        )

        try:
            async with httpx.AsyncClient(timeout=180) as client:
                async with client.stream(
                    "POST",
                    url,
                    headers={
                        "x-goog-api-key": settings.gemini_api_key
                    },
                    json=payload,
                ) as response:

                    response.raise_for_status()

                    async for line in response.aiter_lines():

                        if not line.startswith("data:"):
                            continue

                        data = line[5:].strip()

                        if not data:
                            continue

                        try:
                            event = json.loads(data)
                        except json.JSONDecodeError:
                            continue

                        for candidate in event.get("candidates", []):
                            parts = candidate.get(
                                "content", {}
                            ).get("parts", [])

                            for part in parts:
                                text = part.get("text", "")

                                if text:
                                    yield text

        except httpx.HTTPError as error:
            raise ProviderError(
                f"Gemini streaming failed: {error}"
            ) from error

    # ==========================================
    # NVIDIA NORMAL CHAT
    # ==========================================

    async def _ask_nvidia(self, messages, model):

        if not settings.nvidia_api_key:
            raise ProviderError("NVIDIA API key is not configured.")

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "max_tokens": 2048,
        }

        try:
            async with httpx.AsyncClient(timeout=180) as client:
                response = await client.post(
                    f"{settings.nvidia_base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.nvidia_api_key}"
                    },
                    json=payload,
                )

                response.raise_for_status()

            choices = response.json().get("choices", [])

            if not choices:
                raise ProviderError("NVIDIA returned no choices.")

            answer = choices[0]["message"]["content"]

            if not answer or not answer.strip():
                raise ProviderError("NVIDIA returned an empty response.")

            return answer.strip()

        except httpx.HTTPError as error:
            raise ProviderError(f"NVIDIA failed: {error}") from error

    # ==========================================
    # NVIDIA STREAMING
    # ==========================================

    async def _stream_nvidia(self, messages, model):

        if not settings.nvidia_api_key:
            raise ProviderError("NVIDIA API key is not configured.")

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "max_tokens": 2048,
        }

        try:
            async with httpx.AsyncClient(timeout=180) as client:
                async with client.stream(
                    "POST",
                    f"{settings.nvidia_base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.nvidia_api_key}",
                        "Accept": "text/event-stream",
                    },
                    json=payload,
                ) as response:

                    response.raise_for_status()

                    async for line in response.aiter_lines():

                        if not line.startswith("data:"):
                            continue

                        data = line[5:].strip()

                        if not data or data == "[DONE]":
                            continue

                        try:
                            event = json.loads(data)
                        except json.JSONDecodeError:
                            continue

                        choices = event.get("choices", [])

                        if not choices:
                            continue

                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")

                        if isinstance(content, str) and content:
                            yield content

        except httpx.HTTPError as error:
            raise ProviderError(
                f"NVIDIA streaming failed: {error}"
            ) from error


provider_manager = ProviderManager()
