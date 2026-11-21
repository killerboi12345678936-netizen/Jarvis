
import logging
import time
from datetime import datetime, timedelta, timezone

import httpx
from icalendar import Calendar
import recurring_ical_events

from backend.core.config import settings


logger = logging.getLogger(__name__)


CACHE_SECONDS = 300

_cache = {
    "events": [],
    "fetched_at": 0.0,
    "error": None,
}


def _to_utc_datetime(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

    # All-day events arrive as date objects.
    return datetime(
        value.year,
        value.month,
        value.day,
        tzinfo=timezone.utc,
    )


async def _fetch_ics_bytes():
    if settings.calendar_ics_file:
        with open(settings.calendar_ics_file, "rb") as handle:
            return handle.read()

    if settings.calendar_ics_url:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(settings.calendar_ics_url)

            response.raise_for_status()

            return response.content

    return None


def _parse_ics(content, range_start, range_end):
    calendar = Calendar.from_ical(content)

    expanded = recurring_ical_events.of(calendar).between(
        range_start,
        range_end,
    )

    events = []

    for event in expanded:
        try:
            start = _to_utc_datetime(event.decoded("DTSTART"))
            end_value = event.decoded("DTEND", None)

            if end_value is None:
                end = start + timedelta(hours=1)
            else:
                end = _to_utc_datetime(end_value)

            events.append({
                "title": str(event.get("SUMMARY", "Untitled event")),
                "start": start.isoformat(),
                "end": end.isoformat(),
                "source": "ics",
            })

        except Exception as error:
            logger.warning("Skipping malformed ICS event: %s", error)

    return events


async def get_ics_events(days=14):
    now = datetime.now(timezone.utc)
    range_end = now + timedelta(days=days)

    cached_age = time.time() - _cache["fetched_at"]

    if (
        cached_age < CACHE_SECONDS
        and not _cache["error"]
        and _cache["events"]
    ):
        return _filter_window(_cache["events"], now, range_end)

    try:
        content = await _fetch_ics_bytes()

        if content is None:
            return []

        _cache["events"] = _parse_ics(content, now, range_end)
        _cache["fetched_at"] = time.time()
        _cache["error"] = None

    except Exception as error:
        logger.warning("Could not read calendar ICS: %s", error)

        _cache["error"] = str(error)

        if _cache["events"]:
            return _filter_window(_cache["events"], now, range_end)

        return []

    return _filter_window(_cache["events"], now, range_end)


def _filter_window(events, start, end):
    window = []

    for event in events:
        event_start = datetime.fromisoformat(event["start"])
        event_end = datetime.fromisoformat(event["end"])

        if event_end >= start and event_start <= end:
            window.append(event)

    return sorted(window, key=lambda item: item["start"])
