
import json

import pytest

from backend.integrations.telegram import digest as digest_module
from backend.integrations.telegram.digest import (
    _extract_json,
    _format_messages,
    build_digest,
)


def test_extract_json_variants():
    assert _extract_json('{"a": 1}') == {"a": 1}

    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}

    assert _extract_json('Sure!\n{"a": {"b": 2}} hope that helps') == {
        "a": {"b": 2},
    }

    with pytest.raises(json.JSONDecodeError):
        _extract_json("no json here")


def test_format_messages_builds_subject_block():
    text = _format_messages(
        "Mathematics",
        {
            "title": "Math Study Group",
            "messages": [
                {
                    "sender": "Alice",
                    "date": "2026-11-20T14:30:00+00:00",
                    "text": "Problem set due Monday",
                },
                {"sender": "Bob", "date": "", "text": ""},
                {"sender": None, "date": "2026-11-21T09:00:00", "text": "hi"},
            ],
        },
    )

    lines = text.splitlines()

    assert lines[0] == "SUBJECT: Mathematics"
    assert lines[1] == "GROUP: Math Study Group"
    assert (
        lines[2] == "[2026-11-20 14:30] Alice: Problem set due Monday"
    )
    assert "[2026-11-21 09:00] unknown: hi" == lines[3]

    assert len(lines) == 4


def test_format_messages_truncates_long_text():
    text = _format_messages(
        "Physics",
        {
            "messages": [
                {"sender": "Cara", "date": "", "text": "x" * 600},
            ],
        },
    )

    message_line = text.splitlines()[1]

    assert len(message_line) == 509
    assert message_line.endswith("x" * 500)


@pytest.fixture()
def fake_fetch(monkeypatch):
    groups = {
        "Mathematics": {
            "configured": True,
            "messages": [
                {
                    "sender": "Alice",
                    "date": "2026-11-20T10:00:00",
                    "text": "Assignment 3 due Friday",
                },
            ],
        },
        "Physics": {
            "configured": True,
            "messages": [
                {"sender": "Bob", "date": "", "text": None},
            ],
        },
        "Chemistry": {
            "configured": False,
            "error": "not configured",
            "messages": [],
        },
    }

    async def fetch(hours=24):
        return groups

    monkeypatch.setattr(
        "backend.integrations.telegram.client.fetch_recent_messages",
        fetch,
    )

    return groups


def test_build_digest_classifies_and_reports_errors(fake_fetch, monkeypatch):
    captured = {}

    async def fake_ask(messages, **kwargs):
        captured["prompt"] = messages[1]["content"]

        return json.dumps({
            "announcements": [" midterm next week"],
            "assignments": [
                {"title": "Assignment 3", "details": "", "deadline": "Friday"}
            ],
            "deadlines": [],
            "important": [],
            "summary": "One assignment due Friday.",
        })

    monkeypatch.setattr(
        digest_module.provider_manager,
        "ask",
        fake_ask,
    )

    result = __import__("asyncio").run(build_digest(hours=48))

    assert result["hours"] == 48

    math = result["subjects"]["Mathematics"]

    assert math["messages_read"] == 1
    assert math["data"]["assignments"][0]["title"] == "Assignment 3"
    assert math["data"]["summary"] == "One assignment due Friday."

    assert "SUBJECT: Mathematics" in captured["prompt"]
    assert "Assignment 3 due Friday" in captured["prompt"]

    physics = result["subjects"]["Physics"]

    assert physics["messages_read"] == 1
    assert physics["data"]["summary"] == "No text messages in this period."

    chemistry = result["subjects"]["Chemistry"]

    assert chemistry["messages_read"] == 0
    assert chemistry["error"] == "not configured"
    assert chemistry["data"] is None


def test_build_digest_falls_back_to_raw_on_bad_json(fake_fetch, monkeypatch):
    async def fake_ask(messages, **kwargs):
        return "I could not produce valid JSON, sorry."

    monkeypatch.setattr(
        digest_module.provider_manager,
        "ask",
        fake_ask,
    )

    result = __import__("asyncio").run(build_digest(hours=24))

    math = result["subjects"]["Mathematics"]

    assert math["data"] is None
    assert "valid JSON" in math["raw_summary"]
