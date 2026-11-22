
import asyncio
import json
import sqlite3
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.routes import actions, chat
from backend.tools.parser import (
    ToolStreamFilter,
    build_tool_prompt,
    normalize_arguments,
    normalize_visible_text,
    parse_tool_json,
)
from backend.tools.registry import TOOLS, WORKSPACE, run_tool
from backend.tools.service import process_tool_calls

# The exact model outputs observed in the user's live chat sessions
# (sessions 37/127 and 37/131 in the Jarvis database).
GET_TIME_OUTPUT = '<<TOOL:{"name": "get_time", "arguments": none}><br>'

TELEGRAM_OUTPUT = '<<TOOL:{"name": "telegram_plan", "arguments": none}><br>'

FAKE_DIGEST = {
    "hours": 168,
    "subjects": {
        "mathematics": {
            "title": "A-Star Aspirants",
            "messages_read": 3,
            "data": {
                "announcements": [],
                "assignments": [{
                    "title": "Volume questions Ex4,5",
                    "details": None,
                    "deadline": "2026-11-24",
                }],
                "deadlines": [],
                "recordings": [],
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
                "announcements": [],
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
            "date": "2026-11-24",
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


# ---- Parser: exact real-world outputs --------------------------------

def test_parses_exact_get_time_output_from_real_request():
    stream_filter = ToolStreamFilter()
    visible = stream_filter.feed(GET_TIME_OUTPUT) + stream_filter.finish()

    assert stream_filter.tool_calls == [("get_time", {})]
    assert "TOOL" not in visible
    assert "<<" not in visible


def test_parses_exact_telegram_plan_output_from_real_request():
    stream_filter = ToolStreamFilter()
    visible = (
        stream_filter.feed(TELEGRAM_OUTPUT) + stream_filter.finish()
    )

    assert stream_filter.tool_calls == [("telegram_plan", {})]
    assert "TOOL" not in visible


def test_single_bracket_and_extra_brace_variants():
    for raw in (
        '<TOOL:{"name": "get_time", "arguments": {}}>',
        '<<TOOL:{"name": "get_time", "arguments": {}}}>',
    ):
        stream_filter = ToolStreamFilter()
        stream_filter.feed(raw)
        stream_filter.finish()

        assert stream_filter.tool_calls == [("get_time", {})]


def test_bare_tool_name_without_json():
    stream_filter = ToolStreamFilter()
    stream_filter.feed("<<TOOL:get_time>>")
    stream_filter.finish()

    assert stream_filter.tool_calls == [("get_time", {})]


def test_python_style_dict_body():
    assert parse_tool_json(
        "{'name': 'get_time', 'arguments': {}}"
    ) == {"name": "get_time", "arguments": {}}


def test_missing_arguments_field_normalized_to_empty_dict():
    stream_filter = ToolStreamFilter()
    stream_filter.feed('<<TOOL:{"name": "system_info"}>>')
    stream_filter.finish()

    assert stream_filter.tool_calls == [("system_info", {})]


def test_string_arguments_normalized_to_empty_dict():
    stream_filter = ToolStreamFilter()
    stream_filter.feed('<<TOOL:{"name": "get_time", "arguments": "null"}>>')
    stream_filter.finish()

    assert stream_filter.tool_calls == [("get_time", {})]


def test_tool_name_whitespace_and_case_normalized():
    stream_filter = ToolStreamFilter()
    stream_filter.feed('<<TOOL:{"name": " Get_Time ", "arguments": {}}>>')
    stream_filter.finish()

    assert stream_filter.tool_calls == [("get_time", {})]


def test_unknown_tool_name_hidden_from_visible_text():
    stream_filter = ToolStreamFilter()
    visible = stream_filter.feed(
        '<<TOOL:{"name": "time_machine", "arguments": {}}>>'
    ) + stream_filter.finish()

    assert stream_filter.tool_calls == [("time_machine", {})]
    assert visible == ""


def test_unparseable_markup_held_out_of_visible_text():
    stream_filter = ToolStreamFilter()
    visible = stream_filter.feed("<<TOOL:oops>>") + stream_filter.finish()

    assert stream_filter.tool_calls == []
    assert stream_filter.invalid_blocks
    assert visible == ""


def test_chunked_stream_registers_call_exactly_once():
    stream_filter = ToolStreamFilter()

    for index in range(0, len(GET_TIME_OUTPUT), 2):
        visible = stream_filter.feed(GET_TIME_OUTPUT[index:index + 2])

        assert "TOOL" not in visible

    visible = stream_filter.finish()

    assert "TOOL" not in visible
    assert stream_filter.tool_calls == [("get_time", {})]


def test_multiple_tool_calls_in_one_answer():
    answer = (
        "Checking both.\n"
        + GET_TIME_OUTPUT
        + '\n<<TOOL:{"name": "system_info", "arguments": {}}>>'
    )

    stream_filter = ToolStreamFilter()
    visible = stream_filter.feed(answer) + stream_filter.finish()

    assert stream_filter.tool_calls == [
        ("get_time", {}),
        ("system_info", {}),
    ]
    assert "TOOL" not in visible


def test_normalizer_helpers():
    assert normalize_arguments(None) == {}
    assert normalize_arguments("none") == {}
    assert normalize_arguments("NULL") == {}
    assert normalize_arguments("{}") == {}
    assert normalize_arguments({"a": 1}) == {"a": 1}
    assert normalize_arguments("junk") == {}

    assert normalize_visible_text("a<br>b<br/>c<BR>d") == "a\nb\nc\nd"


def test_tool_prompt_teaches_zero_argument_calls():
    prompt = build_tool_prompt()

    assert '"arguments": {}' in prompt
    assert "Never write none or null" in prompt
    assert "<br>" in prompt


# ---- Dispatcher -------------------------------------------------------

def test_process_tool_calls_executes_get_time_for_real():
    parts, pending, results = asyncio.run(
        process_tool_calls([("get_time", {})])
    )

    assert pending == []

    parsed = datetime.fromisoformat(results[0]["result"]["local_time"])

    assert abs(
        parsed - datetime.now(timezone.utc).astimezone()
    ).total_seconds() < 60


def test_process_tool_calls_unknown_tool_reports_back_to_model():
    parts, pending, results = asyncio.run(
        process_tool_calls([("time_machine", {})])
    )

    assert pending == []
    assert "Unknown tool 'time_machine'" in parts[0]
    assert "get_time" in parts[0]
    assert results[0]["error"]


def test_process_tool_calls_telegram_plan_uses_configured_groups(
    monkeypatch,
):
    digest_calls = {"count": 0}

    async def fake_build_digest(hours):
        digest_calls["count"] += 1

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

    parts, pending, results = asyncio.run(
        process_tool_calls([("telegram_plan", {})])
    )

    assert pending == []
    assert digest_calls["count"] == 1
    assert "MATHEMATICS" in parts[0]
    assert "SUGGESTED STUDY PLAN" in parts[0]


def test_approval_required_tool_is_proposed_not_executed(temp_db):
    parts, pending, results = asyncio.run(process_tool_calls([
        (
            "create_note",
            {"filename": "pipeline_not_created.txt", "content": "hi"},
        ),
    ]))

    assert parts == []
    assert results == []
    assert len(pending) == 1
    assert pending[0]["tool"] == "create_note"

    assert not (WORKSPACE / "pipeline_not_created.txt").exists()


def test_run_tool_get_time_returns_local_time():
    result = asyncio.run(run_tool("get_time", {}))

    parsed = datetime.fromisoformat(result["local_time"])

    assert parsed.tzinfo is not None


# ---- Chat routes: end to end -----------------------------------------

def build_app():
    app = FastAPI()
    app.include_router(chat.router)
    app.include_router(actions.router)

    return app


class FakeStream:
    """Per-round canned provider output; records the messages it was
    given so tests can assert what the pipeline fed back to the model."""

    def __init__(self, rounds):
        self.rounds = rounds
        self.calls = []

    async def __call__(self, messages, provider=None, model=None):
        self.calls.append([dict(m) for m in messages])

        for chunk in self.rounds[len(self.calls) - 1]:
            yield chunk


def _parse_events(raw):
    events = []

    for line in raw.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))

    return events


def _last_assistant_message(db_path):
    conn = sqlite3.connect(db_path)

    row = conn.execute(
        "SELECT content FROM messages "
        "WHERE role = 'assistant' ORDER BY id DESC LIMIT 1"
    ).fetchone()

    conn.close()

    return row[0]


def test_stream_get_time_dispatches_and_answers_naturally(
    temp_db,
    monkeypatch,
):
    fake_stream = FakeStream([
        [GET_TIME_OUTPUT],
        ["It is currently ", "10:15 in the morning."],
    ])

    monkeypatch.setattr(chat.provider_manager, "stream", fake_stream)

    client = TestClient(build_app())

    with client.stream(
        "POST",
        "/api/chat/stream",
        json={
            "message": "Hey Jarvis, what's the time right now?",
            "provider": "ollama",
            "model": "test-model",
        },
    ) as response:
        assert response.status_code == 200

        events = _parse_events(response.read().decode("utf-8"))

    done = events[-1]

    assert done["type"] == "done"
    assert done["pending_actions"] == []
    assert "It is currently 10:15 in the morning." == done["response"]
    assert "TOOL" not in done["response"]
    assert "<<" not in done["response"]

    # The tool really ran: the follow-up fed to round 2 carries the
    # actual local time produced by get_time.
    follow_up = fake_stream.calls[1][-1]["content"]

    assert follow_up.startswith("TOOL_RESULT get_time:")

    payload = json.loads(
        follow_up[follow_up.find("{"):follow_up.rfind("}") + 1]
    )

    parsed = datetime.fromisoformat(payload["local_time"])

    assert abs(
        parsed - datetime.now(timezone.utc).astimezone()
    ).total_seconds() < 60

    # History contains the natural answer, never raw markup.
    assert "It is currently 10:15" in _last_assistant_message(temp_db)
    assert "TOOL" not in _last_assistant_message(temp_db)


def test_stream_telegram_plan_dispatches_without_asking_for_groups(
    temp_db,
    monkeypatch,
):
    # Force the model-driven path so this test exercises the tool
    # pipeline rather than the deterministic intent route.
    monkeypatch.setattr(chat, "match_study_intent", lambda text: False)

    digest_calls = {"count": 0}

    async def fake_build_digest(hours):
        digest_calls["count"] += 1

        return FAKE_DIGEST

    async def fake_get_upcoming(days):
        return []

    async def fake_build_study_plan(tasks, events=None, days=7):
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

    fake_stream = FakeStream([
        [TELEGRAM_OUTPUT],
        ["Here is your weekly plan, based on all three configured "
         "groups. Start with the Mathematics assignment."],
    ])

    monkeypatch.setattr(chat.provider_manager, "stream", fake_stream)

    client = TestClient(build_app())

    with client.stream(
        "POST",
        "/api/chat/stream",
        json={
            "message": (
                "Hey, can you check my Telegram groups and summarise "
                "what I should do for this week?"
            ),
            "provider": "ollama",
            "model": "test-model",
        },
    ) as response:
        assert response.status_code == 200

        events = _parse_events(response.read().decode("utf-8"))

    done = events[-1]

    assert done["type"] == "done"
    assert done["pending_actions"] == []

    # Dispatched exactly once - no duplicate execution.
    assert digest_calls["count"] == 1

    # The full report was returned to the model as the tool result,
    # and the model answered naturally on top of it.
    follow_up = fake_stream.calls[1][-1]["content"]

    assert follow_up.startswith("TOOL_RESULT telegram_plan:")
    assert "MATHEMATICS" in follow_up
    assert "CHEMISTRY" in follow_up
    assert "SUGGESTED STUDY PLAN" in follow_up

    response_text = done["response"]

    assert response_text == (
        "Here is your weekly plan, based on all three configured "
        "groups. Start with the Mathematics assignment."
    )
    assert "TOOL" not in response_text
    assert "<<" not in response_text

    lowered = response_text.lower()

    assert "group names" not in lowered
    assert "more specific details" not in lowered


def test_stream_unknown_tool_retried_with_valid_tool(temp_db, monkeypatch):
    fake_stream = FakeStream([
        ['<<TOOL:{"name": "time_machine", "arguments": {}}>>'],
        [GET_TIME_OUTPUT],
        ["That tool is not available; it is currently ", "10:15."],
    ])

    monkeypatch.setattr(chat.provider_manager, "stream", fake_stream)

    client = TestClient(build_app())

    with client.stream(
        "POST",
        "/api/chat/stream",
        json={
            "message": "what is the time?",
            "provider": "ollama",
            "model": "test-model",
        },
    ) as response:
        events = _parse_events(response.read().decode("utf-8"))

    done = events[-1]

    assert "Unknown tool 'time_machine'" in (
        fake_stream.calls[1][-1]["content"]
    )
    assert "TOOL_RESULT get_time" in fake_stream.calls[2][-1]["content"]
    assert done["response"] == "That tool is not available; it is currently 10:15."
    assert "TOOL" not in done["response"]


def test_stream_malformed_markup_retried_then_honest_fallback(
    temp_db,
    monkeypatch,
):
    fake_stream = FakeStream([
        ["<<TOOL:oops>>"],
        ["<<TOOL:garbage ", "again>>"],
    ])

    monkeypatch.setattr(chat.provider_manager, "stream", fake_stream)

    client = TestClient(build_app())

    with client.stream(
        "POST",
        "/api/chat/stream",
        json={
            "message": "what is the time?",
            "provider": "ollama",
            "model": "test-model",
        },
    ) as response:
        events = _parse_events(response.read().decode("utf-8"))

    done = events[-1]

    correction = fake_stream.calls[1][-1]["content"]

    assert "could not be parsed" in correction

    assert done["response"] == (
        "(I could not prepare that action just now. Please try again.)"
    )
    assert "TOOL" not in done["response"]
    assert "<<" not in done["response"]


def test_non_streaming_get_time_dispatches_and_answers(temp_db, monkeypatch):
    answers = iter([
        GET_TIME_OUTPUT,
        "It is currently 10:15.",
    ])

    seen_messages = []

    async def fake_ask(**kwargs):
        seen_messages.append([dict(m) for m in kwargs["messages"]])

        return next(answers)

    monkeypatch.setattr(chat.provider_manager, "ask", fake_ask)

    client = TestClient(build_app())

    response = client.post(
        "/api/chat/",
        json={
            "message": "Hey Jarvis, what's the time right now?",
            "provider": "ollama",
            "model": "test-model",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["response"] == "It is currently 10:15."
    assert "TOOL" not in data["response"]

    follow_up = seen_messages[1][-1]["content"]

    assert follow_up.startswith("TOOL_RESULT get_time:")
    assert "local_time" in follow_up


def test_stream_tool_failure_surfaced_without_internal_syntax(
    temp_db,
    monkeypatch,
):
    # Force the model-driven path; this phrasing would otherwise hit
    # the deterministic study-intent route.
    monkeypatch.setattr(chat, "match_study_intent", lambda text: False)

    async def failing_build_digest(hours):
        raise RuntimeError("telethon disconnected")

    monkeypatch.setattr(
        "backend.integrations.telegram.digest.build_digest",
        failing_build_digest,
    )

    fake_stream = FakeStream([
        [TELEGRAM_OUTPUT],
        ["I could not read your groups right now; please try again."],
    ])

    monkeypatch.setattr(chat.provider_manager, "stream", fake_stream)

    client = TestClient(build_app())

    with client.stream(
        "POST",
        "/api/chat/stream",
        json={
            "message": "summarise my study groups",
            "provider": "ollama",
            "model": "test-model",
        },
    ) as response:
        events = _parse_events(response.read().decode("utf-8"))

    done = events[-1]

    follow_up = fake_stream.calls[1][-1]["content"]

    assert "TOOL_RESULT telegram_plan: failed" in follow_up
    assert "telethon disconnected" in follow_up
    assert done["response"] == (
        "I could not read your groups right now; please try again."
    )
    assert "TOOL" not in done["response"]
