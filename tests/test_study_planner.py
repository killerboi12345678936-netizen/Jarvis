
"""Study planner tests.

Every clock time in a plan must come from datetime arithmetic in
backend/integrations/planning.py - the model never writes times, and
the validation layer rejects anything a 3B model might have computed
wrong (09:80, overlapping sessions, calendar collisions, invented
assignments).
"""

import asyncio
import copy
import json
from datetime import date, datetime, time, timedelta, timezone

from backend.integrations import planning
from backend.integrations.planning import (
    add_minutes,
    default_blocks,
    free_slots_for_day,
    parse_due_date,
    parse_hhmm,
    parse_time_of_day,
    validate_plan,
)

LOCAL_TZ = datetime.now().astimezone().tzinfo


def _minutes(hhmm):
    hour, minute = parse_hhmm(hhmm)
    return hour * 60 + minute


def _event_on(day, start_local, end_local):
    """Calendar event on `day` at local wall-clock times, stored in
    UTC ISO like the real calendar tables."""

    start = datetime.combine(day, start_local, tzinfo=LOCAL_TZ)
    end = datetime.combine(day, end_local, tzinfo=LOCAL_TZ)

    return {
        "title": "Busy",
        "start": start.astimezone(timezone.utc).isoformat(),
        "end": end.astimezone(timezone.utc).isoformat(),
    }


# ---- Time arithmetic ---------------------------------------------------

def test_add_minutes_0800_plus_60_is_0900():
    assert add_minutes("08:00", 60) == "09:00"


def test_add_minutes_0920_plus_60_is_1020():
    assert add_minutes("09:20", 60) == "10:20"


def test_add_minutes_crosses_hour_boundary():
    assert add_minutes("08:50", 20) == "09:10"
    assert add_minutes("09:45", 45) == "10:30"


def test_add_minutes_crosses_midnight():
    assert add_minutes("23:30", 60) == "00:30"
    assert add_minutes("23:59", 1) == "00:00"
    assert add_minutes("23:00", 24 * 60) == "23:00"


def test_add_minutes_rejects_invalid_input():
    assert add_minutes("08:60", 10) is None
    assert add_minutes("garbage", 10) is None
    assert add_minutes("08:00", -5) is None
    assert add_minutes("08:00", 12.5) is None


def test_parse_hhmm_rejects_invalid_minutes_60_and_80():
    assert parse_hhmm("08:60") is None
    assert parse_hhmm("09:80") is None
    assert parse_hhmm("25:00") is None
    assert parse_hhmm("8:5") is None
    assert parse_hhmm("not a time") is None
    assert parse_hhmm(None) is None

    assert parse_hhmm("08:00") == (8, 0)
    assert parse_hhmm("13:20") == (13, 20)
    assert parse_hhmm("9:05") == (9, 5)


def test_parse_time_of_day_ampm_conversion():
    assert parse_time_of_day("1:20 PM") == (13, 20)
    assert parse_time_of_day("1:20 pm") == (13, 20)
    assert parse_time_of_day("1:20 AM") == (1, 20)
    assert parse_time_of_day("3:20 p.m.") == (15, 20)
    assert parse_time_of_day("11:00 AM") == (11, 0)


def test_parse_time_of_day_noon_and_midnight():
    assert parse_time_of_day("12:00 PM") == (12, 0)
    assert parse_time_of_day("12:30 pm") == (12, 30)
    assert parse_time_of_day("12:00 AM") == (0, 0)
    assert parse_time_of_day("12:05 am") == (0, 5)


def test_parse_time_of_day_rejects_invalid_minutes_60_and_80():
    assert parse_time_of_day("9:80 AM") is None
    assert parse_time_of_day("1:60 PM") is None
    assert parse_time_of_day("13:20 PM") is None
    assert parse_time_of_day("whatever") is None


def test_parse_due_date_understands_common_formats():
    today = date(2026, 11, 22)

    assert parse_due_date("2026-11-25", today) == date(2026, 11, 25)
    assert parse_due_date("25-11-2026", today) == date(2026, 11, 25)
    assert parse_due_date("tomorrow", today) == date(2026, 11, 23)
    # 2026-11-22 is a Sunday; the coming Friday is 2026-11-27.
    assert parse_due_date("due by Friday", today) == date(2026, 11, 27)


def test_parse_due_date_never_invents():
    today = date(2026, 11, 22)

    assert parse_due_date("sometime next month", today) is None
    assert parse_due_date("", today) is None
    assert parse_due_date(None, today) is None


# ---- Free slots and scheduling -----------------------------------------

def test_free_slots_split_around_busy_interval():
    day = date(2026, 11, 23)

    events = [_event_on(day, time(10, 0), time(12, 0))]

    slots = free_slots_for_day(events, day, LOCAL_TZ)

    assert [(s.strftime("%H:%M"), e.strftime("%H:%M")) for s, e in slots] == [
        ("08:00", "10:00"),
        ("12:00", "22:00"),
    ]


def test_free_slots_empty_day_runs_0800_to_2200():
    day = date(2026, 11, 23)

    slots = free_slots_for_day([], day, LOCAL_TZ)

    assert [(s.strftime("%H:%M"), e.strftime("%H:%M")) for s, e in slots] == [
        ("08:00", "22:00")
    ]


def test_distribute_places_blocks_in_free_time_with_breaks():
    day = date(2026, 11, 23)

    blocks = [
        {"subject": "mathematics", "task": "Assignment A",
         "duration_minutes": 60, "priority": 1},
        {"subject": "physics", "task": "Test B",
         "duration_minutes": 60, "priority": 1},
        {"subject": "chemistry", "task": "Recording C",
         "duration_minutes": 30, "priority": 2},
    ]

    plan = planning._distribute(
        blocks, [], [], LOCAL_TZ, 2, day
    )

    day_blocks = plan["days"][0]["blocks"]

    assert [
        (b["start"], b["end"]) for b in day_blocks
    ] == [
        ("08:00", "09:00"),
        ("09:10", "10:10"),
        ("10:20", "10:50"),
    ]

    ok, problems = validate_plan(plan, [], LOCAL_TZ, [])

    assert ok, problems


def test_distribute_never_schedules_over_calendar_events():
    day = date(2026, 11, 23)

    events = [_event_on(day, time(10, 0), time(12, 0))]

    blocks = [
        {"subject": "mathematics", "task": "Assignment A",
         "duration_minutes": 60, "priority": 1},
        {"subject": "physics", "task": "Test B",
         "duration_minutes": 90, "priority": 1},
    ]

    plan = planning._distribute(blocks, [], events, LOCAL_TZ, 2, day)

    day_blocks = plan["days"][0]["blocks"]

    # 60 min fits the 08:00-10:00 morning slot; the 90 min block
    # cannot, so it moves past the busy interval.
    assert (day_blocks[0]["start"], day_blocks[0]["end"]) == (
        "08:00", "09:00"
    )
    assert (day_blocks[1]["start"], day_blocks[1]["end"]) == (
        "12:00", "13:30"
    )

    for block in day_blocks:
        start = _minutes(block["start"])
        end = _minutes(block["end"])

        assert end <= 10 * 60 or start >= 12 * 60


def test_distribute_overflowing_blocks_listed_as_unscheduled():
    day = date(2026, 11, 23)

    blocks = [
        {"subject": "mathematics", "task": "Impossible block",
         "duration_minutes": 900, "priority": 1},
    ]

    plan = planning._distribute(blocks, [], [], LOCAL_TZ, 1, day)

    # A 15-hour session never fits inside the 08:00-22:00 window.
    assert plan["unscheduled"] == ["Impossible block"]
    assert all(not d["blocks"] for d in plan["days"])


def test_validate_plan_rejects_unreasonably_long_sessions():
    plan = {
        "days": [{
            "date": "2026-11-23",
            "blocks": [{
                "subject": "mathematics", "task": "A",
                "duration_minutes": 300, "start": "08:00", "end": "13:00",
            }],
        }],
    }

    ok, problems = validate_plan(plan, [], LOCAL_TZ, [])

    assert not ok
    assert any("session too long" in p for p in problems)


def test_validate_plan_rejects_invalid_times_60_and_80_minutes():
    plan = {
        "days": [{
            "date": "2026-11-23",
            "blocks": [{
                "subject": "mathematics", "task": "A",
                "duration_minutes": 60, "start": "08:60", "end": "09:80",
            }],
        }],
    }

    ok, problems = validate_plan(plan, [], LOCAL_TZ, [])

    assert not ok
    assert any("invalid time" in p for p in problems)


def test_validate_plan_rejects_end_before_start():
    plan = {
        "days": [{
            "date": "2026-11-23",
            "blocks": [{
                "subject": "mathematics", "task": "A",
                "duration_minutes": 60, "start": "09:00", "end": "08:00",
            }],
        }],
    }

    ok, problems = validate_plan(plan, [], LOCAL_TZ, [])

    assert not ok
    assert any("end before start" in p for p in problems)


def test_validate_plan_rejects_overlapping_sessions():
    plan = {
        "days": [{
            "date": "2026-11-23",
            "blocks": [
                {"subject": "mathematics", "task": "A",
                 "duration_minutes": 60, "start": "08:00", "end": "09:00"},
                {"subject": "physics", "task": "B",
                 "duration_minutes": 60, "start": "08:30", "end": "09:30"},
            ],
        }],
    }

    ok, problems = validate_plan(plan, [], LOCAL_TZ, [])

    assert not ok
    assert any("overlapping sessions" in p for p in problems)


def test_validate_plan_requires_break_between_sessions():
    plan = {
        "days": [{
            "date": "2026-11-23",
            "blocks": [
                {"subject": "mathematics", "task": "A",
                 "duration_minutes": 60, "start": "08:00", "end": "09:00"},
                {"subject": "physics", "task": "B",
                 "duration_minutes": 30, "start": "09:05", "end": "09:35"},
            ],
        }],
    }

    ok, problems = validate_plan(plan, [], LOCAL_TZ, [])

    assert not ok
    assert any("missing break" in p for p in problems)


def test_validate_plan_rejects_duration_mismatch():
    plan = {
        "days": [{
            "date": "2026-11-23",
            "blocks": [{
                "subject": "mathematics", "task": "A",
                "duration_minutes": 45, "start": "08:00", "end": "09:00",
            }],
        }],
    }

    ok, problems = validate_plan(plan, [], LOCAL_TZ, [])

    assert not ok
    assert any("duration mismatch" in p for p in problems)


def test_validate_plan_detects_calendar_conflict():
    day = date(2026, 11, 23)

    events = [_event_on(day, time(10, 30), time(12, 30))]

    plan = {
        "days": [{
            "date": day.isoformat(),
            "blocks": [{
                "subject": "mathematics", "task": "A",
                "duration_minutes": 60, "start": "10:00", "end": "11:00",
            }],
        }],
    }

    ok, problems = validate_plan(plan, events, LOCAL_TZ, [])

    assert not ok
    assert any("conflicts with calendar event" in p for p in problems)


def test_validate_plan_accepts_conflict_free_day():
    day = date(2026, 11, 23)

    events = [_event_on(day, time(10, 30), time(12, 30))]

    plan = {
        "days": [{
            "date": day.isoformat(),
            "blocks": [{
                "subject": "mathematics", "task": "A",
                "duration_minutes": 60, "start": "08:00", "end": "09:00",
            }],
        }],
    }

    ok, problems = validate_plan(plan, events, LOCAL_TZ, [])

    assert ok, problems


def test_validate_plan_rejects_unbacked_tasks_without_suggestion_flag():
    tasks = [{
        "subject": "mathematics", "kind": "assignment",
        "title": "Volume questions Ex4,5", "due": "2026-11-24",
    }]

    plan = {
        "days": [{
            "date": "2026-11-23",
            "blocks": [{
                "subject": "mathematics",
                "task": "Revise entire organic chemistry chapter 12",
                "duration_minutes": 30, "start": "08:00", "end": "08:30",
            }],
        }],
    }

    ok, problems = validate_plan(plan, [], LOCAL_TZ, tasks)

    assert not ok
    assert any("not found in sources" in p for p in problems)


# ---- Task inventory -----------------------------------------------------

def test_default_blocks_keep_source_tasks_distinct_per_subject():
    tasks = [
        {"subject": "mathematics", "kind": "assignment",
         "title": "Volume questions Ex4,5", "due": "2026-11-24"},
        {"subject": "physics", "kind": "test",
         "title": "Kinematics test", "due": "2026-11-23"},
        {"subject": "chemistry", "kind": "deadline",
         "title": "Lab report", "due": None},
        {"subject": "mathematics", "kind": "recording",
         "title": "Lecture 12 recording", "due": None},
    ]

    blocks = default_blocks(tasks, date(2026, 11, 22))

    produced = [(b["subject"], b["task"]) for b in blocks]

    assert produced == [
        ("physics", "Kinematics test"),
        ("mathematics", "Volume questions Ex4,5"),
        ("chemistry", "Lab report"),
        ("mathematics", "Lecture 12 recording"),
    ]

    # Tests first, nearest deadline first, no duplicated or generic
    # task text.
    assert len({b["task"] for b in blocks}) == len(blocks)


def test_normalize_tasks_drops_unusable_entries():
    normalized = planning.normalize_tasks([
        {"subject": "mathematics", "kind": "assignment",
         "title": "Real task", "due": None},
        {"subject": "physics", "title": "", "kind": "assignment"},
        "just a string",
        None,
        {"subject": "chemistry", "kind": "assignment"},
    ])

    assert normalized == [{
        "subject": "mathematics", "kind": "assignment",
        "title": "Real task", "due": None,
    }]


def test_sanitize_model_blocks_drops_invented_assignments():
    tasks = [
        {"subject": "mathematics", "kind": "assignment",
         "title": "Volume questions Ex4,5", "due": None},
    ]

    sanitized = planning._sanitize_model_blocks({
        "plan_title": "Weekly plan",
        "blocks": [
            {"subject": "mathematics", "task": "Volume questions Ex4,5",
             "duration_minutes": 60, "priority": 1},
            {"subject": "mathematics",
             "task": "Revise entire organic chemistry chapter 12",
             "duration_minutes": 45, "priority": 1},
            {"subject": "history", "task": "Volume questions Ex4,5",
             "duration_minutes": 30, "priority": 2},
        ],
        "notes": "n",
    }, tasks)

    assert [b["task"] for b in sanitized["blocks"]] == [
        "Volume questions Ex4,5"
    ]


def test_sanitize_model_blocks_clamps_extreme_durations():
    tasks = [{
        "subject": "physics", "kind": "test",
        "title": "Kinematics test", "due": None,
    }]

    sanitized = planning._sanitize_model_blocks({
        "plan_title": "p",
        "blocks": [{"subject": "physics", "task": "Kinematics test",
                    "duration_minutes": 500, "priority": 9}],
        "notes": "",
    }, tasks)

    assert sanitized["blocks"][0]["duration_minutes"] == 90
    assert sanitized["blocks"][0]["priority"] == 3


def test_label_suggested_flags_unbacked_blocks():
    tasks = [{
        "subject": "mathematics", "kind": "assignment",
        "title": "Volume questions Ex4,5", "due": None,
    }]

    plan = {"days": [{"date": "2026-11-23", "blocks": [
        {"subject": "mathematics", "task": "Volume questions Ex4,5",
         "duration_minutes": 60},
        {"subject": "mathematics", "task": "General revision",
         "duration_minutes": 30},
    ]}]}

    labelled = planning._label_suggested(plan, tasks)

    assert "suggested" not in labelled["days"][0]["blocks"][0]
    assert labelled["days"][0]["blocks"][1]["suggested"] is True


# ---- Full workflow -------------------------------------------------------

def _fake_provider(answer):
    async def fake_ask(*args, **kwargs):
        return answer

    return fake_ask


def test_build_study_plan_computes_times_from_calendar(monkeypatch):
    day = date.today()

    tasks = [{
        "subject": "mathematics", "kind": "assignment",
        "title": "Volume questions Ex4,5", "due": day.isoformat(),
    }]

    events = [_event_on(day, time(10, 0), time(12, 0))]

    model_answer = json.dumps({
        "plan_title": "Weekly plan",
        "blocks": [{"subject": "mathematics",
                    "task": "Volume questions Ex4,5",
                    "duration_minutes": 60, "priority": 1}],
        "notes": "Start here.",
    })

    monkeypatch.setattr(
        planning.provider_manager, "ask", _fake_provider(model_answer)
    )

    result = asyncio.run(
        planning.build_study_plan(tasks=tasks, events=events, days=3)
    )

    plan = result["plan"]

    assert plan is not None
    assert result.get("validation_problems") is None

    first_day = plan["days"][0]

    assert first_day["date"] == day.isoformat()
    assert first_day["blocks"] == [{
        "subject": "mathematics",
        "task": "Volume questions Ex4,5",
        "duration_minutes": 60,
        "start": "08:00",
        "end": "09:00",
    }]

    ok, problems = validate_plan(plan, events, LOCAL_TZ, tasks)

    assert ok, problems


def test_build_study_plan_does_not_modify_calendar_events(monkeypatch):
    day = date.today()

    tasks = [{
        "subject": "physics", "kind": "test",
        "title": "Kinematics test", "due": None,
    }]

    events = [_event_on(day, time(9, 0), time(10, 0))]

    events_snapshot = copy.deepcopy(events)

    model_answer = json.dumps({
        "plan_title": "p",
        "blocks": [{"subject": "physics", "task": "Kinematics test",
                    "duration_minutes": 60, "priority": 1}],
        "notes": "",
    })

    monkeypatch.setattr(
        planning.provider_manager, "ask", _fake_provider(model_answer)
    )

    result = asyncio.run(
        planning.build_study_plan(tasks=tasks, events=events)
    )

    # The planner reads the calendar; it never creates, edits or
    # deletes anything on it.
    assert events == events_snapshot

    plan = result["plan"]

    assert plan is not None

    ok, problems = validate_plan(plan, events, LOCAL_TZ, tasks)

    assert ok, problems


def test_build_study_plan_ignores_model_invented_tasks(monkeypatch):
    tasks = [{
        "subject": "mathematics", "kind": "assignment",
        "title": "Volume questions Ex4,5", "due": None,
    }]

    model_answer = json.dumps({
        "plan_title": "Invented plan",
        "blocks": [
            {"subject": "mathematics", "task": "Volume questions Ex4,5",
             "duration_minutes": 60, "priority": 1},
            {"subject": "mathematics",
             "task": "Solve 50 integration problems chapter 9",
             "duration_minutes": 90, "priority": 1},
        ],
        "notes": "",
    })

    monkeypatch.setattr(
        planning.provider_manager, "ask", _fake_provider(model_answer)
    )

    result = asyncio.run(planning.build_study_plan(tasks=tasks))

    plan_titles = [
        b["task"]
        for d in result["plan"]["days"]
        for b in d["blocks"]
    ]

    assert plan_titles == ["Volume questions Ex4,5"]


def test_build_study_plan_with_empty_groups_plans_nothing(monkeypatch):
    empty_answer = json.dumps({
        "plan_title": "Anything",
        "blocks": [{"subject": "mathematics",
                    "task": "Invented generic revision",
                    "duration_minutes": 60, "priority": 1}],
        "notes": "",
    })

    monkeypatch.setattr(
        planning.provider_manager, "ask", _fake_provider(empty_answer)
    )

    result = asyncio.run(planning.build_study_plan(tasks=[]))

    plan = result["plan"]

    assert all(not d["blocks"] for d in plan["days"])
    assert plan.get("subjects_without_tasks") is None

    # Nothing invented anywhere in the rendered plan.
    rendered = json.dumps(plan)

    assert "Invented generic revision" not in rendered


def test_build_study_plan_reports_subjects_without_scheduled_tasks(
    monkeypatch,
):
    tasks = [
        {"subject": "mathematics", "kind": "assignment",
         "title": "Volume questions Ex4,5", "due": None},
        {"subject": "chemistry", "kind": "deadline",
         "title": "Lab report", "due": None},
    ]

    model_answer = json.dumps({
        "plan_title": "p",
        "blocks": [{"subject": "mathematics",
                    "task": "Volume questions Ex4,5",
                    "duration_minutes": 60, "priority": 1}],
        "notes": "",
    })

    monkeypatch.setattr(
        planning.provider_manager, "ask", _fake_provider(model_answer)
    )

    result = asyncio.run(planning.build_study_plan(tasks=tasks))

    # Chemistry had a real task but the model never scheduled it; the
    # plan must say so instead of staying silent.
    assert result["plan"]["subjects_without_tasks"] == ["chemistry"]


def test_build_study_plan_falls_back_when_model_output_unusable(
    monkeypatch,
):
    tasks = [{
        "subject": "mathematics", "kind": "assignment",
        "title": "Volume questions Ex4,5", "due": None,
    }]

    monkeypatch.setattr(
        planning.provider_manager, "ask", _fake_provider("not json at all")
    )

    result = asyncio.run(planning.build_study_plan(tasks=tasks))

    plan = result["plan"]

    assert plan is not None
    assert "Volume questions Ex4,5" in [
        b["task"] for d in plan["days"] for b in d["blocks"]
    ]
    assert "could not structure" in plan["notes"]


# ---- Report integration --------------------------------------------------

def test_build_study_report_with_empty_groups_is_honest(monkeypatch):
    from backend.integrations.telegram import digest, report

    empty_digest = {
        "hours": 168,
        "subjects": {
            subject: {
                "title": f"{subject} group",
                "messages_read": 0,
                "data": {
                    "announcements": [],
                    "assignments": [],
                    "deadlines": [],
                    "recordings": [],
                    "important": [],
                    "summary": "No messages.",
                },
            }
            for subject in ("mathematics", "physics", "chemistry")
        },
    }

    async def fake_build_digest(hours):
        return empty_digest

    async def bomb_build_study_plan(*args, **kwargs):
        raise AssertionError("planner must not run for empty groups")

    monkeypatch.setattr(
        digest, "build_digest", fake_build_digest
    )
    monkeypatch.setattr(
        planning, "build_study_plan", bomb_build_study_plan
    )

    text = asyncio.run(report.build_study_report(hours=168))

    assert "No assignments, tests or deadlines were found" in text
    assert "will not invent tasks" in text
    assert "SUGGESTED STUDY PLAN" not in text
