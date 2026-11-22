
import asyncio
import json
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.tools import registry
from backend.tools.permissions import (
    claim_action,
    get_action,
    propose_action,
    recover_stale_actions,
)


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    target = tmp_path / "workspace"
    target.mkdir()

    monkeypatch.setattr(registry, "WORKSPACE", target)

    return target


def test_create_note_writes_exact_content(workspace):
    result = registry.create_note({
        "filename": "Jarvis.txt",
        "content": "Hello Rajesh",
    })

    path = workspace / "Jarvis.txt"

    assert path.exists()
    assert path.read_text(encoding="utf-8") == "Hello Rajesh"

    assert result["created"] is True
    assert result["verified"] is True
    assert result["filename"] == "Jarvis.txt"
    assert result["location"] == str(path)
    assert result["bytes"] == len("Hello Rajesh".encode("utf-8"))


@pytest.mark.parametrize(
    "filename",
    [
        "../evil.txt",
        "..\\evil.txt",
        "sub/evil.txt",
        "sub\\evil.txt",
        "..",
        "C:/temp/evil.txt",
        "C:\\temp\\evil.txt",
        "/etc/passwd",
        "note.txt.exe",
        "note",
        ".txt",
        "a" * 90 + ".txt",
    ],
)
def test_create_note_rejects_path_traversal(workspace, filename):
    with pytest.raises(ValueError):
        registry.create_note({"filename": filename, "content": "x"})

    assert list(workspace.iterdir()) == []


def test_create_note_refuses_overwrite(workspace):
    (workspace / "Jarvis.txt").write_text("original", encoding="utf-8")

    with pytest.raises(ValueError, match="already exists"):
        registry.create_note({
            "filename": "Jarvis.txt",
            "content": "replacement",
        })

    assert (workspace / "Jarvis.txt").read_text(
        encoding="utf-8"
    ) == "original"


def test_create_note_validates_content(workspace):
    with pytest.raises(ValueError, match="empty"):
        registry.create_note({"filename": "a.txt", "content": "   "})

    with pytest.raises(ValueError, match="too long"):
        registry.create_note({
            "filename": "a.txt",
            "content": "x" * 20001,
        })


def test_read_and_list_workspace_tools(workspace):
    (workspace / "notes.txt").write_text("hello", encoding="utf-8")

    listed = registry.list_workspace_files({})

    assert listed == {"files": ["notes.txt"]}

    read = registry.read_workspace_file({"filename": "notes.txt"})

    assert read["content"] == "hello"

    with pytest.raises(ValueError, match="Invalid filename|outside"):
        registry.read_workspace_file({"filename": "../notes.txt"})

    with pytest.raises(ValueError, match="not found|Not found"):
        registry.read_workspace_file({"filename": "missing.txt"})


def test_stale_executing_actions_are_recovered(temp_db):
    action_id = asyncio.run(propose_action("create_note", {}))

    asyncio.run(claim_action(action_id))

    action = asyncio.run(get_action(action_id))

    assert action["status"] == "executing"

    # The action is fresh, so nothing is recovered yet.
    recovered = asyncio.run(recover_stale_actions(max_age_seconds=600))

    assert recovered == 0

    # Age the row past the cutoff, then recovery must fail it.
    import aiosqlite
    from backend.memory.database import DB_PATH

    old_timestamp = "2020-01-01T00:00:00+00:00"

    async def age_row():
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE tool_actions SET updated_at = ? WHERE id = ?",
                (old_timestamp, action_id),
            )
            await db.commit()

    asyncio.run(age_row())

    recovered = asyncio.run(recover_stale_actions(max_age_seconds=600))

    assert recovered == 1

    action = asyncio.run(get_action(action_id))

    assert action["status"] == "failed"
    assert "interrupted" in action["result"].lower()


def _actions_app():
    from backend.api.routes.actions import router

    app = FastAPI()
    app.include_router(router)

    return app


def test_approve_endpoint_executes_exactly_once(
    temp_db,
    workspace,
    monkeypatch,
):
    client = TestClient(_actions_app())

    action_id = asyncio.run(
        propose_action(
            "create_note",
            {"filename": "Jarvis.txt", "content": "Hello Rajesh"},
        )
    )

    response = client.post(f"/api/actions/{action_id}/approve")

    assert response.status_code == 200
    body = response.json()

    assert body["success"] is True
    assert body["result"]["verified"] is True
    assert body["result"]["filename"] == "Jarvis.txt"

    assert (workspace / "Jarvis.txt").read_text(
        encoding="utf-8"
    ) == "Hello Rajesh"

    # A retried approval must not execute a second time.
    retry = client.post(f"/api/actions/{action_id}/approve")

    assert retry.status_code == 409
    assert "already" in retry.json()["detail"]

    action = asyncio.run(get_action(action_id))

    assert action["status"] == "approved"


def test_failed_action_records_error(
    temp_db,
    workspace,
):
    client = TestClient(_actions_app())

    # Overwrite attempt: the file already exists, so execution must
    # fail and record the reason rather than touching the file.
    (workspace / "Jarvis.txt").write_text("original", encoding="utf-8")

    action_id = asyncio.run(
        propose_action(
            "create_note",
            {"filename": "Jarvis.txt", "content": "Hello Rajesh"},
        )
    )

    response = client.post(f"/api/actions/{action_id}/approve")

    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]

    action = asyncio.run(get_action(action_id))

    assert action["status"] == "failed"
    assert "already exists" in action["result"]


def test_traversal_tool_call_fails_at_execution(temp_db, workspace):
    client = TestClient(_actions_app())

    action_id = asyncio.run(
        propose_action(
            "create_note",
            {"filename": "../evil.txt", "content": "nope"},
        )
    )

    response = client.post(f"/api/actions/{action_id}/approve")

    assert response.status_code == 400

    action = asyncio.run(get_action(action_id))

    assert action["status"] == "failed"

    # Nothing was created outside the workspace.
    assert not (workspace.parent / "evil.txt").exists()
