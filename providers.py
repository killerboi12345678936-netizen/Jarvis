import requests
from config import settings

class ProviderError(RuntimeError):
    pass

def ask_ai(provider, model, messages):
    if provider == "ollama":
        try:
            r = requests.post(settings.ollama_url + "/api/chat", json={"model":model,"messages":messages,"stream":False}, timeout=180)
            r.raise_for_status()
            return r.json().get("message",{}).get("content","").strip() or "[Empty response]"
        except requests.RequestException as e:
            raise ProviderError(f"Ollama request failed: {e}") from e
    if provider == "gemini":
        if not settings.gemini_api_key:
            raise ProviderError("Set GEMINI_API_KEY in .env first.")
        system = "\\n\\n".join(m["content"] for m in messages if m["role"] == "system")
        contents = [{"role":"model" if m["role"]=="assistant" else "user","parts":[{"text":m["content"]}]} for m in messages if m["role"]!="system"]
        payload = {"contents":contents}
        if system:
            payload["systemInstruction"] = {"parts":[{"text":system}]}
        try:
            r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", headers={"x-goog-api-key":settings.gemini_api_key}, json=payload, timeout=180)
            r.raise_for_status()
            return "".join(p.get("text","") for p in r.json()["candidates"][0]["content"]["parts"]).strip()
        except (requests.RequestException, KeyError, IndexError, ValueError) as e:
            raise ProviderError(f"Gemini request failed: {e}") from e
    if provider == "nvidia":
        if not settings.nvidia_api_key:
            raise ProviderError("Set NVIDIA_API_KEY in .env first.")
        try:
            r = requests.post(settings.nvidia_base_url+"/chat/completions", headers={"Authorization":f"Bearer {settings.nvidia_api_key}"}, json={"model":model,"messages":messages,"stream":False,"max_tokens":2048}, timeout=180)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        except (requests.RequestException, KeyError, IndexError, ValueError) as e:
            raise ProviderError(f"NVIDIA request failed: {e}") from e
    raise ProviderError("Unknown provider.")
