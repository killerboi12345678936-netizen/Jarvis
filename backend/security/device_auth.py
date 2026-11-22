
import secrets
from pathlib import Path

from starlette.types import ASGIApp, Receive, Scope, Send


PROJECT_ROOT = Path(__file__).resolve().parents[2]

TOKEN_FILE = PROJECT_ROOT / "data" / "device_token.txt"

_token_cache = None


def get_device_token():
    """Load the shared device token, creating one on first use.

    Every client (desktop browser, phone) must present this token via
    the X-Device-Token header or ?token= query parameter. It gates all
    /api endpoints and WebSocket connections."""

    global _token_cache

    if _token_cache:
        return _token_cache

    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    else:
        token = secrets.token_hex(16)
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(token, encoding="utf-8")

    _token_cache = token
    return token


def extract_token(message, query_string):
    """Find the device token in a header or the query string."""

    for name, value in message.get("headers", []):
        if name.lower() == b"x-device-token":
            return value.decode("latin-1").strip()

    if query_string:
        for part in query_string.split(b"&"):
            key, _, value = part.partition(b"=")
            if key == b"token":
                return value.decode("latin-1").strip()

    return None


class DeviceAuthMiddleware:
    """Rejects requests and WebSocket connections that do not carry
    the shared device token. CORS preflight (OPTIONS) passes through
    so browsers can still discover allowed origins, and /health stays
    open for launchers and uptime checks."""

    def __init__(self, app, enabled=True):
        self.app = app
        self.enabled = enabled

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        path = scope.get("path", "")

        # The pairing endpoint is the one way in without a token: it
        # validates the presented code itself and stores nothing.
        if path == "/api/auth/pair" and scope.get("method") == "POST":
            await self.app(scope, receive, send)
            return

        if (
            not self.enabled
            or scope["type"] not in ("http", "websocket")
            or not path.startswith("/api")
            or (
                scope["type"] == "http"
                and scope.get("method") == "OPTIONS"
            )
        ):
            await self.app(scope, receive, send)
            return

        provided = extract_token(
            scope,
            scope.get("query_string", b""),
        )

        if provided and secrets.compare_digest(
            provided, get_device_token()
        ):
            await self.app(scope, receive, send)
            return

        if scope["type"] == "websocket":
            # Reject before accept; uvicorn turns this into a closed
            # connection with the custom status code.
            await send({"type": "websocket.close", "code": 4401})
            return

        response = b'{"detail":"Unauthorized device. Provide the Jarvis device token."}'
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(response)).encode()),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": response,
        })
