
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.core.config import settings
from backend.integrations.calendar import ics
from backend.memory.database import get_event_by_id
from backend.tools.registry import run_tool


@pytest.fixture(autouse=True)
def clean_ics_cache():
    ics._cache.update({"events": [], "fetched_at": 0.0, "error": None})
    yield
    ics._cache.update({"events": [], "fetched_at": 0.0, "error": None})


SAMPLE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//JarvisTest//EN
BEGIN:VEVENT
UID:lecture-1@test
DTSTAMP:20261121T000000Z
DTSTART:20261125T140000Z
DTEND:20261125T150000Z
SUMMARY:Physics lecture
END:VEVENT
BEGIN:VEVENT
UID:allday-1@test
DTSTAMP:20261121T000000Z
DTSTART;VALUE=DATE:20261126
DTEND;VALUE=DATE:20261127
SUMMARY:All-day workshop
END:VEVENT
BEGIN:VEVENT
UID:weekly-1@test
DTSTAMP:20261121T000000Z
DTSTART:20261123T100000Z
DTEND:20261123T110000Z
SUMMARY:Weekly sync
RRULE:FREQ=WEEKLY
END:VEVENT
END:VCALENDAR
"""


def use_ics_file(monkeypatch, tmp_path):
    ics_file = tmp_path / "calendar.ics"
    ics_file.write_text(SAMPLE_ICS, encoding="utf-8")

    monkeypatch.setattr(settings, "calendar_ics_file", str(ics_file))
    monkeypatch.setattr(settings, "calendar_ics_url", "")

    ics._cache.update({"events": [], "fetched_at": 0.0, "error": None})

    return ics_file


def test_parse_ics_events(monkeypatch, tmp_path):
    use_ics_file(monkeypatch, tmp_path)

    events = asyncio.run(ics.get_ics_events(days=14))

    titles = [event["title"] for event in events]

    assert "Physics lecture" in titles
    assert "All-day workshop" in titles
    assert titles.count("Weekly sync") == 2

    lecture = next(
        event for event in events
        if event["title"] == "Physics lecture"
    )

    assert lecture["start"] == "2026-11-25T14:00:00+00:00"
    assert lecture["end"] == "2026-11-25T15:00:00+00:00"
    assert lecture["source"] == "ics"

    workshop = next(
        event for event in events
        if event["title"] == "All-day workshop"
    )

    assert workshop["start"] == "2026-11-26T00:00:00+00:00"
    assert workshop["end"] == "2026-11-27T00:00:00+00:00"


def test_parse_ics_caches(monkeypatch, tmp_path):
    ics_file = use_ics_file(monkeypatch, tmp_path)

    first = asyncio.run(ics.get_ics_events(days=14))
    ics_file.unlink()
    second = asyncio.run(ics.get_ics_events(days=14))

    assert len(first) == len(second) == 4


def test_get_upcoming_merges_local_and_ics(monkeypatch, tmp_path, temp_db):
    use_ics_file(monkeypatch, tmp_path)

    from backend.memory.database import (
        create_calendar_event,
        init_db,
    )

    asyncio.run(init_db())

    now = datetime.now(timezone.utc)

    asyncio.run(create_calendar_event(
        "Dentist appointment",
        (now + timedelta(days=1)).isoformat(),
        (now + timedelta(days=1, hours=1)).isoformat(),
        "bring insurance card",
    ))

    from backend.integrations.calendar import service

    events = asyncio.run(service.get_upcoming(days=14))

    sources = {event["source"] for event in events}

    assert sources == {"ics", "local"}

    local = next(
        event for event in events
        if event["source"] == "local"
    )

    assert local["title"] == "Dentist appointment"
    assert local["notes"] == "bring insurance card"


def test_find_free_slots():
    service = __import__(
        "backend.integrations.calendar.service",
        fromlist=["find_free_slots"],
    )

    day_start = datetime(2026, 11, 25, 8, 0, tzinfo=timezone.utc)
    day_end = datetime(2026, 11, 25, 22, 0, tzinfo=timezone.utc)

    events = [
        {"start": "2026-11-25T09:00:00+00:00",
         "end": "2026-11-25T10:30:00+00:00",
         "title": "A"},
        {"start": "2026-11-25T10:00:00+00:00",
         "end": "2026-11-25T11:00:00+00:00",
         "title": "B overlaps A"},
        {"start": "2026-11-25T15:00:00+00:00",
         "end": "2026-11-25T16:00:00+00:00",
         "title": "C"},
    ]

    slots = service.find_free_slots(events, day_start, day_end)

    assert slots[0]["start"] == day_start.isoformat()
    assert slots[0]["end"] == "2026-11-25T09:00:00+00:00"
    assert slots[1]["start"] == "2026-11-25T11:00:00+00:00"
    assert slots[1]["end"] == "2026-11-25T15:00:00+00:00"
    assert slots[1]["minutes"] == 240
    assert slots[2]["end"] == day_end.isoformat()
    assert all(slot["minutes"] >= 30 for slot in slots)


def test_find_free_slots_fully_booked():
    service = __import__(
        "backend.integrations.calendar.service",
        fromlist=["find_free_slots"],
    )

    day_start = datetime(2026, 11, 25, 8, 0, tzinfo=timezone.utc)
    day_end = datetime(2026, 11, 25, 22, 0, tzinfo=timezone.utc)

    events = [
        {"start": day_start.isoformat(),
         "end": day_end.isoformat(),
         "title": "all day"},
    ]

    assert service.find_free_slots(events, day_start, day_end) == []


def test_calendar_status_route(temp_db):
    from backend.main import app

    client = TestClient(app)

    response = client.get("/api/integrations/calendar/status")

    assert response.status_code == 200

    data = response.json()

    assert data["ics_url_configured"] is False
    assert data["ics_file_configured"] is False


def test_local_event_crud_flow(temp_db):
    from backend.main import app

    client = TestClient(app)

    created = client.post(
        "/api/integrations/calendar/events",
        json={
            "title": "Study group",
            "start": "2026-11-25T18:00",
            "end": "2026-11-25T20:00",
            "notes": "chapter 4",
        },
    )

    assert created.status_code == 200

    event_id = created.json()["event_id"]

    stored = asyncio.run(get_event_by_id(event_id))

    assert stored["title"] == "Study group"
    assert stored["notes"] == "chapter 4"
    assert stored["start_utc"].endswith("+00:00")

    updated = client.put(
        f"/api/integrations/calendar/events/{event_id}",
        json={"title": "Study group moved", "notes": None},
    )

    assert updated.status_code == 200

    stored = asyncio.run(get_event_by_id(event_id))

    assert stored["title"] == "Study group moved"
    assert stored["notes"] == "chapter 4"

    deleted = client.delete(
        f"/api/integrations/calendar/events/{event_id}"
    )

    assert deleted.status_code == 200

    missing = client.delete(
        f"/api/integrations/calendar/events/{event_id}"
    )

    assert missing.status_code == 404


def test_local_event_validation(temp_db):
    from backend.main import app

    client = TestClient(app)

    bad_range = client.post(
        "/api/integrations/calendar/events",
        json={
            "title": "Backwards",
            "start": "2026-11-25T18:00",
            "end": "2026-11-25T17:00",
        },
    )

    assert bad_range.status_code == 400

    bad_date = client.post(
        "/api/integrations/calendar/events",
        json={
            "title": "Bad date",
            "start": "not-a-date",
            "end": "2026-11-25T17:00",
        },
    )

    assert bad_date.status_code == 400

    missing = client.put(
        "/api/integrations/calendar/events/999999",
        json={"title": "Ghost"},
    )

    assert missing.status_code == 404


def test_upcoming_route(temp_db):
    from backend.main import app

    client = TestClient(app)

    response = client.get("/api/integrations/calendar/upcoming?days=3")

    assert response.status_code == 200
    assert "events" in response.json()


def test_read_calendar_tool(temp_db):
    result = asyncio.run(
        run_tool("read_calendar", {"days": 5})
    )

    assert result["days"] == 5
    assert result["events"] == []


def test_create_and_delete_event_tools(temp_db):
    created = asyncio.run(run_tool("create_event", {
        "title": "Physics revision",
        "start": "2026-11-26T16:00",
        "end": "2026-11-26T17:30",
        "notes": "momentum problems",
    }))

    assert created["created"] is True

    event_id = created["event_id"]

    stored = asyncio.run(get_event_by_id(event_id))

    assert stored["title"] == "Physics revision"

    deleted = asyncio.run(
        run_tool("delete_event", {"event_id": event_id})
    )

    assert deleted["deleted"] is True

    assert asyncio.run(get_event_by_id(event_id)) is None


def test_delete_event_tool_rejects_unknown(temp_db):
    try:
        asyncio.run(
            run_tool("delete_event", {"event_id": 123456})
        )
    except ValueError as error:
        assert "No local event" in str(error)
    else:
        raise AssertionError("Expected ValueError for unknown event_id")


def test_create_event_tool_rejects_bad_dates(temp_db):
    for start, end in (
        ("garbage", "2026-11-26T17:00"),
        ("2026-11-26T17:00", "2026-11-26T16:00"),
    ):
        try:
            asyncio.run(run_tool("create_event", {
                "title": "Bad",
                "start": start,
                "end": end,
            }))
        except ValueError:
            pass
        else:
            raise AssertionError(
                f"Expected ValueError for start={start}, end={end}"
            )


def test_create_event_approval_flow(temp_db):
    from backend.main import app

    client = TestClient(app)

    proposed = client.post(
        "/api/actions/propose",
        json={
            "tool_name": "create_event",
            "arguments": {
                "title": "Math homework block",
                "start": "2026-11-27T10:00",
                "end": "2026-11-27T11:00",
            },
        },
    )

    assert proposed.status_code == 200

    data = proposed.json()

    assert data["status"] == "pending"

    action_id = data["action_id"]

    approved = client.post(f"/api/actions/{action_id}/approve")

    assert approved.status_code == 200

    result = approved.json()["result"]

    stored = asyncio.run(get_event_by_id(result["event_id"]))

    assert stored["title"] == "Math homework block"

    client.delete(f"/api/integrations/calendar/events/{result['event_id']}")

    actions = client.get("/api/actions?status=approved").json()["actions"]

    assert any(action["id"] == action_id for action in actions)
