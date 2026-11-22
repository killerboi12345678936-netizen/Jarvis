
import asyncio

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from backend.security import device_auth
from backend.security.device_auth import DeviceAuthMiddleware


@pytest.fixture()
def token(monkeypatch):
    monkeypatch.setattr(device_auth, "_token_cache", "unit-test-token")

    return "unit-test-token"


@pytest.fixture()
def app(token):
    application = FastAPI()

    application.add_middleware(DeviceAuthMiddleware, enabled=True)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/api/thing")
    async def thing():
        return {"ok": True}

    @application.get("/health")
    async def health():
        return {"ok": True}

    @application.websocket("/api/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept()
        await websocket.send_text("hello")
        await websocket.close()

    return application


def test_request_without_token_is_rejected(app):
    client = TestClient(app)

    response = client.get("/api/thing")

    assert response.status_code == 401
    assert "device token" in response.json()["detail"]


def test_request_with_header_token_passes(app, token):
    client = TestClient(app)

    response = client.get("/api/thing", headers={"X-Device-Token": token})

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_request_with_query_token_passes(app, token):
    client = TestClient(app)

    response = client.get(f"/api/thing?token={token}")

    assert response.status_code == 200


def test_wrong_token_is_rejected(app):
    client = TestClient(app)

    response = client.get("/api/thing", headers={"X-Device-Token": "nope"})

    assert response.status_code == 401


def test_health_and_preflight_stay_open(app):
    client = TestClient(app)

    assert client.get("/health").status_code == 200

    preflight = client.options(
        "/api/thing",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-device-token",
        },
    )

    assert preflight.status_code in (200, 204)


def test_websocket_without_token_is_closed(app):
    from starlette.testclient import WebSocketDisconnect

    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect) as disconnect:
        with client.websocket_connect("/api/ws"):
            pass

    assert disconnect.value.code == 4401


def test_websocket_with_token_passes(app, token):
    client = TestClient(app)

    with client.websocket_connect(f"/api/ws?token={token}") as websocket:
        assert websocket.receive_text() == "hello"


def test_disabled_middleware_lets_everything_through(token):
    application = FastAPI()
    application.add_middleware(DeviceAuthMiddleware, enabled=False)

    @application.get("/api/thing")
    async def thing():
        return {"ok": True}

    client = TestClient(application)

    assert client.get("/api/thing").status_code == 200


def test_token_file_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(device_auth, "_token_cache", None)
    monkeypatch.setattr(
        device_auth, "TOKEN_FILE", tmp_path / "device_token.txt"
    )

    first = device_auth.get_device_token()

    assert len(first) == 32

    second = device_auth.get_device_token()

    assert first == second

    asyncio.run(asyncio.sleep(0))
