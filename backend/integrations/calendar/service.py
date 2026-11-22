
from datetime import datetime, time, timedelta, timezone

from backend.integrations.calendar import ics
from backend.memory.database import list_calendar_events


def _parse_iso(value):
    parsed = datetime.fromisoformat(value)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


async def get_upcoming(days=14):
    start = datetime.now(timezone.utc)
    end = start + timedelta(days=days)

    ics_events = await ics.get_ics_events(days=days)

    local_events = await list_calendar_events(
        start_after=start.isoformat(),
        start_before=end.isoformat(),
    )

    events = list(ics_events)

    for event in local_events:
        events.append({
            "id": event["id"],
            "title": event["title"],
            "start": event["start_utc"],
            "end": event["end_utc"],
            "source": "local",
            "notes": event.get("notes"),
        })

    return sorted(
        events,
        key=lambda item: item["start"],
    )


def _merge_intervals(intervals):
    merged = []

    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))

        else:
            merged.append((start, end))

    return merged


def find_free_slots(events, day_start, day_end, min_minutes=30):
    busy = []

    for event in events:
        try:
            event_start = _parse_iso(event["start"])
            event_end = _parse_iso(event["end"])
        except (KeyError, ValueError):
            continue

        overlap_start = max(event_start, day_start)
        overlap_end = min(event_end, day_end)

        if overlap_start < overlap_end:
            busy.append((overlap_start, overlap_end))

    free = []
    cursor = day_start

    for busy_start, busy_end in _merge_intervals(busy):
        if busy_start - cursor >= timedelta(minutes=min_minutes):
            free.append((cursor, busy_start))

        cursor = max(cursor, busy_end)

    if day_end - cursor >= timedelta(minutes=min_minutes):
        free.append((cursor, day_end))

    return [
        {
            "start": slot_start.isoformat(),
            "end": slot_end.isoformat(),
            "minutes": int(
                (slot_end - slot_start).total_seconds() // 60
            ),
        }
        for slot_start, slot_end in free
    ]


def describe_schedule(events, days=7):
    day_start_time = time(8, 0)
    day_end_time = time(22, 0)

    lines = []
    now = datetime.now(timezone.utc).astimezone()

    for offset in range(days):
        local_day = (now + timedelta(days=offset)).date()

        day_start = datetime.combine(
            local_day,
            day_start_time,
            tzinfo=now.tzinfo,
        ).astimezone(timezone.utc)

        day_end = datetime.combine(
            local_day,
            day_end_time,
            tzinfo=now.tzinfo,
        ).astimezone(timezone.utc)

        day_events = [
            event for event in events
            if day_start <= _parse_iso(event["start"]) < day_end
        ]

        slots = find_free_slots(day_events, day_start, day_end)

        busy_text = (
            "; ".join(
                f"{event['title']} "
                f"{_parse_iso(event['start']).astimezone(now.tzinfo):%H:%M}"
                f"-{_parse_iso(event['end']).astimezone(now.tzinfo):%H:%M}"
                for event in day_events
            )
            or "none"
        )

        slots_text = (
            "; ".join(
                f"{slot['start'][-13:-8]}-{slot['end'][-13:-8]} "
                f"({slot['minutes']} min)"
                for slot in slots
            )
            or "none"
        )

        lines.append(
            f"{local_day.isoformat()} ({local_day.strftime('%A')}): "
            f"busy: {busy_text}. free slots: {slots_text}"
        )

    return "\n".join(lines)


async def build_calendar_study_plan(days=7, deadlines_text=""):
    events = await get_upcoming(days=days)

    schedule_text = describe_schedule(events, days=days)

    tasks = [
        {
            "subject": "general",
            "kind": "assignment",
            "title": line.strip(),
            "due": None,
        }
        for line in (deadlines_text or "").splitlines()
        if line.strip()
    ]

    from backend.integrations.planning import build_study_plan

    plan = await build_study_plan(
        tasks=tasks,
        events=events,
        days=days,
    )

    return {
        "kind": "calendar",
        "days": days,
        "schedule": schedule_text,
        **plan,
    }
