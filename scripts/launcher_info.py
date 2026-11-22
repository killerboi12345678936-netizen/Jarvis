
"""Print launcher facts as LABEL=VALUE lines for start_jarvis.bat.

Labels: LANIP, SCHEME, TOKEN, OLLAMA (up/down), OLLAMA_MODEL."""

import json
import socket
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.5)
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"


def device_token():
    import sys

    sys.path.insert(0, str(PROJECT_ROOT))

    from backend.security.device_auth import get_device_token

    return get_device_token()


def ollama_status():
    try:
        with urllib.request.urlopen(
            "http://localhost:11434/api/tags", timeout=3
        ) as response:
            data = json.loads(response.read().decode("utf-8"))
            models = [m.get("name", "") for m in data.get("models", [])]
            return "up", ", ".join(models[:4]) or "no models pulled"
    except Exception:
        return "down", ""


def main():
    scheme = "http"

    certs = PROJECT_ROOT / "data" / "certs"

    if (certs / "dev.crt").exists() and (certs / "dev.key").exists():
        scheme = "https"

    ollama, models = ollama_status()

    print(f"LANIP={lan_ip()}")
    print(f"SCHEME={scheme}")
    print(f"TOKEN={device_token()}")
    print(f"OLLAMA={ollama}")
    print(f"OLLAMA_MODELS={models}")


if __name__ == "__main__":
    main()
