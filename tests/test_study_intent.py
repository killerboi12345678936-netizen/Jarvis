
import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.routes import actions, chat
from backend.integrations.telegram import report as report_module
from backend.integrations.telegram.report import (
    build_study_report,
    build_study_report_safe,
    format_digest_report,
    format_plan_report,
    match_study_intent,
)
from backend.integrations.telegram.digest import collect_deadlines
from backend.tools.registry import TOOLS, get_tool, run_tool

EXACT_REQUEST = (
    "Read all my latest Mathematics, Physics and Chemistry group "
    "announcements. Identify assignments, upcoming tests, lecture "
    "recordings and deadlines. Organise them into a realistic plan "
    "for today and this week. Don't send anything to Telegram."
)

FAKE_DIGEST = {
    "hours": 168,
    "subjects": {
        "mathematics": {
            "title": "A-Star Aspirants",
            "messages_read": 3,
            "data": {
                "announcements": ["Test on Monday"],
                "assignments": [{
                    "title": "Volume questions Ex4,5",
                    "details": None,
                    "deadline": "2026-11-22",
                }],
                "deadlines": [],
                "recordings": ["zoom.us/j/lecture12"],
                "important": [],
                "summary": "Exam preparation underway.",
            },
        },
        "physics": {
            "title": "A-Star Analysts",
            "messages_read": 0,
            "data": {
                "announcements": [],
                "assignments": [],
                "deadlines": [],
                "recordings": [],
                "important": [],
                "summary": "No text messages in this period.",
            },
        },
        "chemistry": {
            "title": "A-Star Alchemists",
            "messages_read": 2,
            "data": {
                "announcements": ["Lab safety PDF shared"],
                "assignments": [],
                "deadlines": [{"what": "Lab report", "when": "Friday"}],
                "recordings": [],
                "important": [],
                "summary": "Lab work this week.",
            },
        },
    },
}

FAKE_PLAN = {
    "plan": {
        "plan_title": "Weekly Study Plan",
        "days": [{
            "date": "2026-11-22",
            "blocks": [{
                "subject": "Mathematics",
                "task": "Finish Volume questions Ex4,5",
                "duration_minutes": 60,
                "start": "08:00",
                "end": "09:00",
            }],
        }],
        "notes": "Start with the nearest deadline.",
    },
    "raw_plan": None,
}


# ---- Intent routing --------------------------------------------------

def test_exact_user_request_matches_study_intent():
    assert match_study_intent(EXACT_REQUEST) is True


def test_group_content_questions_match():
    assert match_study_intent(
        "any assignments in my maths group today?"
    ) is True

    assert match_study_intent(
        "what deadlines were posted in physics and chemistry?"
    ) is True

    assert match_study_intent("make me a weekly study plan") is True

    assert match_study_intent(
        "Hey, can you check my Telegram groups and summarise what I "
        "should do for this week?"
    ) is True


def test_unrelated_and_calendar_requests_do_not_match():
    assert match_study_intent("what time is it?") is False

    assert match_study_intent("plan my day") is False

    assert match_study_intent(
        "create a calendar event for my physics test tomorrow"
    ) is False

    assert match_study_intent("hello Jarvis") is False


# ---- Workflow helpers -------------------------------------------------

def test_collect_deadlines_flattens_subjects():
    text = collect_deadlines(FAKE_DIGEST)

    assert "[mathematics] assignment: Volume questions Ex4,5" in text
    assert "due 2026-11-22" in text
    assert "[chemistry] Lab report - due Friday" in text


def test_format_digest_report_lists_subjects_and_readonly():
    text = format_digest_report(FAKE_DIGEST)

    assert "MATHEMATICS" in text
    assert "A-Star Aspirants" in text
    assert "PHYSICS" in text
    assert "No messages in this period" in text
    assert "CHEMISTRY" in text
    assert "zoom.us/j/lecture12" in text
    assert "never send" in text.lower()
    assert "no messages in this period, so nothing" in text.lower()


def test_format_plan_report_lists_blocks_without_calendar_changes():
    text = format_plan_report(FAKE_PLAN)

    assert "SUGGESTED STUDY PLAN" in text
    assert "Mathematics: Finish Volume questions Ex4,5" in text
    assert "not created or changed any calendar events" in text
    assert "Start with the nearest deadline." in text


def test_format_plan_report_handles_missing_plan():
    assert format_plan_report({"plan": None, "raw_plan": None}) is None

    fallback = format_plan_report({
        "plan": None,
        "raw_plan": "raw planner text",
    })

    assert "raw planner text" in fallback


def test_build_study_report_combines_digest_and_plan(monkeypatch):
    async def fake_build_digest(hours):
        assert hours == 168
        return FAKE_DIGEST

    async def fake_get_upcoming(days):
        assert days == 7

        return []

    async def fake_build_study_plan(tasks, events=None, days=7):
        assert any(
            task["subject"] == "mathematics" for task in tasks
        )
        assert events == []

        return FAKE_PLAN

    monkeypatch.setattr(
        "backend.integrations.telegram.digest.build_digest",
        fake_build_digest,
    )

    monkeypatch.setattr(
        "backend.integrations.calendar.service.get_upcoming",
        fake_get_upcoming,
    )

    monkeypatch.setattr(
        "backend.integrations.planning.build_study_plan",
        fake_build_study_plan,
    )

    report_text = asyncio.run(build_study_report(hours=168))

    assert "MATHEMATICS" in report_text
    assert "SUGGESTED STUDY PLAN" in report_text


def test_build_study_report_safe_never_raises(monkeypatch):
    async def broken_build_digest(hours):
        raise RuntimeError("network down")

    monkeypatch.setattr(
        "backend.integrations.telegram.digest.build_digest",
        broken_build_digest,
    )

    text = asyncio.run(build_study_report_safe())

    assert "could not read" in text.lower()
    assert "never send" in text.lower()


def test_build_study_report_safe_reports_not_configured(monkeypatch):
    from backend.integrations.telegram.client import TelegramNotConfigured

    async def unconfigured_build_digest(hours):
        raise TelegramNotConfigured("not set up")

    monkeypatch.setattr(
        "backend.integrations.telegram.digest.build_digest",
        unconfigured_build_digest,
    )

    text = asyncio.run(build_study_report_safe())

    assert "not configured yet" in text.lower()


# ---- Registry tools ---------------------------------------------------

def test_telegram_tools_registered_as_automatic_readonly():
    for name in ("telegram_digest", "telegram_plan"):
        tool = get_tool(name)

        assert tool is not None
        assert tool["permission"] == "automatic"

    assert "never send" in TOOLS["telegram_digest"]["description"].lower()


def test_run_tool_telegram_digest(monkeypatch):
    async def fake_build_digest(hours):
        return FAKE_DIGEST

    monkeypatch.setattr(
        "backend.integrations.telegram.digest.build_digest",
        fake_build_digest,
    )

    result = asyncio.run(run_tool("telegram_digest", {}))

    assert result["subjects"]["mathematics"]["messages_read"] == 3


def test_run_tool_telegram_plan(monkeypatch):
    async def fake_report(hours=168):
        return "DIGEST + PLAN TEXT"

    monkeypatch.setattr(
        "backend.integrations.telegram.report.build_study_report",
        fake_report,
    )

    result = asyncio.run(run_tool("telegram_plan", {}))

    assert result["report"] == "DIGEST + PLAN TEXT"


# ---- Chat route regression -------------------------------------------

def build_app():
    app = FastAPI()
    app.include_router(chat.router)
    app.include_router(actions.router)

    return app


def test_chat_request_invokes_telegram_workflow_without_asking(
    temp_db,
    monkeypatch,
):
    calls = {"digest": 0, "llm": 0}

    async def fake_report_safe(hours=168):
        calls["digest"] += 1
        return format_digest_report(FAKE_DIGEST)

    monkeypatch.setattr(
        chat,
        "build_study_report_safe",
        fake_report_safe,
    )

    async def fail_ask(**kwargs):
        calls["llm"] += 1
        raise AssertionError("LLM must not be used for this request")

    monkeypatch.setattr(chat.provider_manager, "ask", fail_ask)
    monkeypatch.setattr(chat.provider_manager, "stream", fail_ask)

    client = TestClient(build_app())

    response = client.post(
        "/api/chat/",
        json={
            "message": EXACT_REQUEST,
            "provider": "ollama",
            "model": "test-model",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert calls["digest"] == 1
    assert calls["llm"] == 0

    assert "MATHEMATICS" in data["response"]
    assert "CHEMISTRY" in data["response"]
    assert "2026-11-22" in data["response"]

    lowered = data["response"].lower()
    assert "provide" not in lowered
    assert "more specific details" not in lowered
    assert "group names" not in lowered


def test_chat_stream_invokes_telegram_workflow(
    temp_db,
    monkeypatch,
):
    async def fake_report_safe(hours=168):
        return format_digest_report(FAKE_DIGEST)

    monkeypatch.setattr(
        chat,
        "build_study_report_safe",
        fake_report_safe,
    )

    async def fail_stream(**kwargs):
        raise AssertionError("LLM must not be used for this request")

    monkeypatch.setattr(chat.provider_manager, "stream", fail_stream)

    client = TestClient(build_app())

    with client.stream(
        "POST",
        "/api/chat/stream",
        json={
            "message": EXACT_REQUEST,
            "provider": "ollama",
            "model": "test-model",
        },
    ) as response:
        assert response.status_code == 200

        raw = response.read().decode("utf-8")

    events = []

    for line in raw.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))

    kinds = [e["type"] for e in events]

    assert kinds[0] == "start"
    assert "chunk" in kinds
    assert kinds[-1] == "done"

    done = events[-1]

    assert "MATHEMATICS" in done["response"]
    assert done["pending_actions"] == []


def test_chat_study_route_falls_back_to_llm_for_other_messages(
    temp_db,
    monkeypatch,
):
    report_calls = []

    async def fake_report_safe(hours=168):
        report_calls.append(hours)
        return "should not be used"

    monkeypatch.setattr(
        chat,
        "build_study_report_safe",
        fake_report_safe,
    )

    async def fake_ask(**kwargs):
        return "The capital of France is Paris."

    monkeypatch.setattr(chat.provider_manager, "ask", fake_ask)

    client = TestClient(build_app())

    response = client.post(
        "/api/chat/",
        json={
            "message": "what is the capital of France?",
            "provider": "ollama",
            "model": "test-model",
        },
    )

    assert response.status_code == 200
    assert response.json()["response"] == "The capital of France is Paris."
    assert report_calls == []
