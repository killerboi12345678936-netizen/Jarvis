
import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.routes import actions, chat
from backend.memory.database import get_messages
from backend.tools import registry
from backend.tools.parser import strip_fake_proposals
from backend.tools.permissions import list_actions

FAKE_NOTE = (
    "Let me create that for you. [Action proposed and awaiting your "
    "approval - create_note: file 'man.txt' with content: 'Hello "
    "Rishi.']. Open the Actions panel (or use the buttons below) to "
    "approve or reject."
)

REAL_CALL = (
    '<<TOOL:{"name": "create_note", "arguments": '
    '{"filename": "man.txt", "content": "Hello Rishi"}}>>'
)


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    target = tmp_path / "workspace"
    target.mkdir()

    monkeypatch.setattr(registry, "WORKSPACE", target)

    return target


def build_app():
    app = FastAPI()
    app.include_router(chat.router)
    app.include_router(actions.router)

    return app


def chat_body(**overrides):
    body = {
        "message": "create one file named man.txt whihc says hello rishi",
        "provider": "ollama",
        "model": "test-model",
    }
    body.update(overrides)
    return body


def strip_sse(raw):
    events = []

    for line in raw.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))

    return events


def first_pending_action():
    rows = asyncio.run(list_actions())

    pending = [r for r in rows if r["status"] == "pending"]

    return pending[0] if pending else None


def test_strip_fake_proposals_removes_copied_notes():
    assert strip_fake_proposals(FAKE_NOTE).strip() == (
        "Let me create that for you."
    )


def test_strip_fake_proposals_without_panel_sentence():
    text = (
        "Sure. [Action proposed and awaiting your approval - "
        "create_note: file 'x.txt' with content: 'hi']"
    )

    assert strip_fake_proposals(text).strip() == "Sure."


def test_strip_fake_proposals_leaves_normal_text():
    text = "I will not propose anything about the Action panel today."

    assert strip_fake_proposals(text) == text


def test_fake_proposal_triggers_correction_and_real_action(
    temp_db, workspace, monkeypatch
):
    answers = [
        FAKE_NOTE,
        REAL_CALL,
    ]

    async def fake_ask(**kwargs):
        return answers.pop(0)

    monkeypatch.setattr(chat.provider_manager, "ask", fake_ask)

    client = TestClient(build_app())

    response = client.post("/api/chat/", json=chat_body())

    assert response.status_code == 200

    data = response.json()

    # The corrective round must have run (both answers consumed).
    assert answers == []

    # Exactly one real proposal note, no fabricated copy.
    assert data["response"].count("[Action proposed") == 1
    assert "file 'man.txt'" in data["response"]

    row = first_pending_action()

    assert row is not None
    assert row["tool_name"] == "create_note"

    arguments = json.loads(row["arguments"])

    assert arguments["filename"] == "man.txt"
    assert arguments["content"] == "Hello Rishi"

    # Approving executes the stored arguments exactly.
    approval = client.post(f"/api/actions/{row['id']}/approve")

    assert approval.status_code == 200
    assert (workspace / "man.txt").read_text(encoding="utf-8") == (
        "Hello Rishi"
    )


def test_persistent_fake_proposal_is_stripped_and_honest(
    temp_db, workspace, monkeypatch
):
    async def fake_ask(**kwargs):
        return FAKE_NOTE

    monkeypatch.setattr(chat.provider_manager, "ask", fake_ask)

    client = TestClient(build_app())

    response = client.post("/api/chat/", json=chat_body())

    assert response.status_code == 200

    data = response.json()

    assert "[Action proposed" not in data["response"]
    assert "could not prepare that action" in data["response"]
    assert first_pending_action() is None


def test_plain_answer_untouched_without_correction(
    temp_db, workspace, monkeypatch
):
    calls = []

    async def fake_ask(**kwargs):
        calls.append(kwargs)
        return "The capital of France is Paris."

    monkeypatch.setattr(chat.provider_manager, "ask", fake_ask)

    client = TestClient(build_app())

    response = client.post(
        "/api/chat/",
        json=chat_body(message="what is the capital of France?"),
    )

    assert response.status_code == 200
    assert response.json()["response"] == (
        "The capital of France is Paris."
    )
    assert len(calls) == 1


def test_stream_route_fake_proposal_corrected(
    temp_db, workspace, monkeypatch
):
    answers = [
        FAKE_NOTE,
        REAL_CALL,
    ]

    async def fake_stream(**kwargs):
        answer = answers.pop(0)

        for start in range(0, len(answer), 9):
            yield answer[start:start + 9]

    monkeypatch.setattr(chat.provider_manager, "stream", fake_stream)

    client = TestClient(build_app())

    with client.stream(
        "POST", "/api/chat/stream", json=chat_body()
    ) as response:
        assert response.status_code == 200

        raw = response.read().decode("utf-8")

    events = strip_sse(raw)
    done = next(e for e in events if e["type"] == "done")

    assert answers == []
    assert done["response"].count("[Action proposed") == 1
    assert any(
        a["tool"] == "create_note"
        and a["arguments"]["filename"] == "man.txt"
        for a in done["pending_actions"]
    )


def test_saved_history_contains_single_real_note(
    temp_db, workspace, monkeypatch
):
    answers = [
        FAKE_NOTE,
        REAL_CALL,
    ]

    async def fake_ask(**kwargs):
        return answers.pop(0)

    monkeypatch.setattr(chat.provider_manager, "ask", fake_ask)

    client = TestClient(build_app())

    response = client.post("/api/chat/", json=chat_body())

    session_id = response.json()["session_id"]

    messages = asyncio.run(get_messages(session_id, limit=5))

    assistant = [m for m in messages if m["role"] == "assistant"]

    assert len(assistant) == 1
    assert assistant[0]["content"].count("[Action proposed") == 1
