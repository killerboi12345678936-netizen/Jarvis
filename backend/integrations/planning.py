
"""Study planning pipeline.

The chat model never computes clock times or invents assignments: it
only picks source-backed tasks, orders them and assigns durations.
This module then schedules the blocks deterministically with real
datetime/timedelta arithmetic inside the student's free calendar
slots, and a validation layer checks the result before it is shown.
"""

import json
import re
from datetime import date, datetime, time, timedelta, timezone

from backend.providers.manager import provider_manager


# Study window in local time (the user's timezone; Asia/Kolkata here).
DAY_START = time(8, 0)
DAY_END = time(22, 0)

BREAK_MINUTES = 10
MIN_SESSION_MINUTES = 20
MAX_SESSION_MINUTES = 90
MAX_BLOCKS_PER_DAY = 6
MAX_DAILY_MINUTES = 480

TEST_RE = re.compile(r"\b(test|exam|quiz|paper)\b", re.IGNORECASE)

HHMM_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")

AMPM_RE = re.compile(
    r"^(\d{1,2}):(\d{2})\s*([ap])\.?m\.?$",
    re.IGNORECASE,
)

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

PLAN_INSTRUCTIONS = """You are Jarvis, a study planner. Below are
1) tasks found in the student's study groups (assignments, tests,
deadlines, lecture recordings) and 2) the student's calendar for the
coming days.

Decide WHAT to study, in WHICH order, and for HOW LONG. The system
computes exact clock times from the calendar, so never write times
yourself.

Return ONLY a JSON object (no markdown fences):
{
  "plan_title": "...",
  "blocks": [
    {"subject": "mathematics|physics|chemistry", "task": "...",
     "duration_minutes": 60, "priority": 1}
  ],
  "notes": "brief advice"
}

Rules:
- Use ONLY tasks from the task list. Never invent assignments, tests
  or deadlines. A revision block must name the task it revises.
- duration_minutes: 45-90 for assignments and tests, 15-30 for
  recordings, 20-30 for revision.
- priority: 1 = nearest or most urgent deadline, 2 = medium,
  3 = routine revision.
- Order the blocks so the most urgent work comes first.
- Do not create blocks for subjects that have no tasks.
"""


# ---- Time helpers (the single place where clock times are made) ------

def parse_hhmm(text):
    """Parse strict 24-hour HH:MM. Returns (hour, minute) or None.

    Minutes of 60, 80 and friends are rejected here: they are the
    classic model arithmetic failure this module exists to prevent."""

    if not isinstance(text, str):
        return None

    match = HHMM_RE.match(text.strip())

    if not match:
        return None

    return int(match.group(1)), int(match.group(2))


def parse_time_of_day(text):
    """Parse "13:20", "1:20 PM" or "1:20 AM" into 24-hour (h, m).

    One deterministic AM/PM conversion instead of ad-hoc string
    fixes; 12:xx stays 12:xx for noon and becomes 00:xx for midnight
    only when explicitly marked AM."""

    if not isinstance(text, str):
        return None

    stripped = text.strip()

    parsed = parse_hhmm(stripped)

    if parsed:
        return parsed

    ampm = AMPM_RE.match(stripped)

    if not ampm:
        return None

    hour = int(ampm.group(1))
    minute = int(ampm.group(2))
    meridiem = ampm.group(3).lower()

    if not 1 <= hour <= 12 or minute > 59:
        return None

    if meridiem == "p" and hour != 12:
        hour += 12

    if meridiem == "a" and hour == 12:
        hour = 0

    return hour, minute


def format_hhmm(hour, minute):
    return f"{hour:02d}:{minute:02d}"


def add_minutes(hhmm, minutes):
    """Add minutes to an HH:MM clock time, crossing hour and day
    boundaries. Returns HH:MM (24h) or None for invalid input."""

    parsed = parse_hhmm(hhmm) if isinstance(hhmm, str) else None

    if parsed is None or not isinstance(minutes, int) or minutes < 0:
        return None

    hour, minute = parsed

    total = hour * 60 + minute + minutes

    total %= 24 * 60

    return format_hhmm(total // 60, total % 60)


def parse_due_date(text, today=None):
    """Best-effort parse of deadline text into a date.

    Understands ISO dates, DD-MM-YY / DD-MM-YYYY, "today", "tomorrow"
    and weekday names. Returns None when the text carries no usable
    date; a None result is never turned into an invented date."""

    if not isinstance(text, str):
        return None

    cleaned = text.strip().lower()
    today = today or date.today()

    try:
        return date.fromisoformat(cleaned[:10])
    except ValueError:
        pass

    numeric = re.match(r"^(\d{1,2})-(\d{1,2})-(\d{2}|\d{4})$", cleaned)

    if numeric:
        day = int(numeric.group(1))
        month = int(numeric.group(2))
        year = int(numeric.group(3))

        if year < 100:
            year += 2000

        try:
            return date(year, month, day)
        except ValueError:
            return None

    if "today" in cleaned:
        return today

    if "tomorrow" in cleaned:
        return today + timedelta(days=1)

    for name, weekday in WEEKDAYS.items():
        if name in cleaned:
            offset = (weekday - today.weekday()) % 7

            return today + timedelta(days=offset)

    return None


# ---- Free slots ------------------------------------------------------

def _event_intervals_utc(events):
    intervals = []

    for event in events or []:
        try:
            event_start = datetime.fromisoformat(event["start"])
            event_end = datetime.fromisoformat(event["end"])
        except (KeyError, TypeError, ValueError):
            continue

        if event_start.tzinfo is None:
            event_start = event_start.replace(tzinfo=timezone.utc)

        if event_end.tzinfo is None:
            event_end = event_end.replace(tzinfo=timezone.utc)

        if event_end <= event_start:
            continue

        intervals.append((event_start, event_end))

    return intervals


def free_slots_for_day(events, local_day, tz):
    """Free intervals on local_day inside the study window, as
    tz-aware datetime pairs, computed from real calendar events."""

    day_start = datetime.combine(local_day, DAY_START, tzinfo=tz)
    day_end = datetime.combine(local_day, DAY_END, tzinfo=tz)

    busy = []

    for event_start, event_end in _event_intervals_utc(events):
        overlap_start = max(event_start.astimezone(tz), day_start)
        overlap_end = min(event_end.astimezone(tz), day_end)

        if overlap_start < overlap_end:
            busy.append((overlap_start, overlap_end))

    merged = []

    for busy_start, busy_end in sorted(busy):
        if merged and busy_start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], busy_end))

        else:
            merged.append((busy_start, busy_end))

    slots = []
    cursor = day_start

    for busy_start, busy_end in merged:
        if busy_end - cursor >= timedelta(minutes=MIN_SESSION_MINUTES):
            slots.append((cursor, busy_start))

        cursor = max(cursor, busy_end)

    if day_end - cursor >= timedelta(minutes=MIN_SESSION_MINUTES):
        slots.append((cursor, day_end))

    return slots


# ---- Task inventory --------------------------------------------------

def normalize_tasks(tasks):
    """Keep only usable, source-backed task entries."""

    normalized = []

    for task in tasks or []:
        if not isinstance(task, dict):
            continue

        title = str(task.get("title") or "").strip()

        if not title:
            continue

        kind = str(task.get("kind") or "assignment").lower()

        normalized.append({
            "subject": str(task.get("subject") or "general").lower(),
            "kind": kind,
            "title": title,
            "due": task.get("due"),
        })

    return normalized


def _task_order_key(task, today):
    due_date = parse_due_date(task.get("due"), today)

    due_rank = (
        due_date.toordinal()
        if due_date
        else today.toordinal() + 1000
    )

    kind_rank = {
        "test": 0,
        "assignment": 1,
        "deadline": 2,
        "recording": 3,
    }.get(task["kind"], 4)

    return (due_rank, kind_rank)


def default_blocks(tasks, today=None):
    """Deterministic fallback schedule when the model output is
    unusable: one block per source task with kind-based durations."""

    today = today or date.today()

    ordered = sorted(
        tasks,
        key=lambda task: _task_order_key(task, today),
    )

    blocks = []

    for task in ordered:
        duration = {
            "test": 90,
            "assignment": 60,
            "deadline": 45,
            "recording": 25,
        }.get(task["kind"], 30)

        blocks.append({
            "subject": task["subject"],
            "task": task["title"],
            "duration_minutes": duration,
            "priority": 1,
        })

    return blocks


def _sanitize_model_blocks(data, tasks):
    """Accept the model's block list only when it references source
    tasks; invented entries are dropped, not shown as facts."""

    today = date.today()

    if not isinstance(data, dict):
        return None

    raw_blocks = data.get("blocks")

    if not isinstance(raw_blocks, list):
        return None

    known_subjects = {task["subject"] for task in tasks}

    blocks = []

    for item in raw_blocks[:40]:
        if not isinstance(item, dict):
            continue

        task_text = str(item.get("task") or "").strip()

        if not task_text:
            continue

        subject = str(item.get("subject") or "").strip().lower()

        if subject not in known_subjects:
            continue

        try:
            duration = int(item.get("duration_minutes"))
        except (TypeError, ValueError):
            continue

        duration = max(15, min(duration, MAX_SESSION_MINUTES))

        try:
            priority = int(item.get("priority"))
        except (TypeError, ValueError):
            priority = 2

        priority = max(1, min(priority, 3))

        # Only attach task text that actually exists in the sources;
        # the model may not rename or invent assignments. Unmatched
        # entries are dropped, never shown as facts.
        matched = _match_source_task(task_text, tasks)

        if matched is None:
            continue

        blocks.append({
            "subject": subject,
            "task": matched["title"],
            "duration_minutes": duration,
            "priority": priority,
        })

    return {
        "plan_title": str(data.get("plan_title") or "Study plan")[:120],
        "blocks": blocks,
        "notes": str(data.get("notes") or "")[:500],
    }


def _match_source_task(task_text, tasks):
    words = set(re.findall(r"[a-z0-9]+", task_text.lower()))

    best = None
    best_overlap = 0.0

    for task in tasks:
        source_words = set(
            re.findall(r"[a-z0-9]+", task["title"].lower())
        )

        if not source_words:
            continue

        overlap = len(words & source_words) / len(source_words)

        if overlap > best_overlap:
            best = task
            best_overlap = overlap

    if best is not None and best_overlap >= 0.5:
        return best

    return None


# ---- Deterministic scheduling ----------------------------------------

def _distribute(blocks, tasks, events, tz, days, start_date):
    """Place ordered blocks into real free slots across days.

    All clock times come from datetime arithmetic; no model output
    ever reaches a clock display."""

    today = start_date

    ordered = sorted(
        enumerate(blocks),
        key=lambda pair: (
            pair[1].get("priority", 2),
            _task_order_key(
                {"kind": "assignment", "due": _due_for(pair[1], tasks)},
                today,
            ),
            pair[0],
        ),
    )

    ordered = [block for _, block in ordered]

    plan_days = []
    remaining = list(ordered)

    for offset in range(days):
        local_day = start_date + timedelta(days=offset)

        slots = free_slots_for_day(events, local_day, tz)

        day_blocks = []
        day_minutes = 0

        for slot_start, slot_end in slots:
            cursor = slot_start

            while (
                remaining
                and len(day_blocks) < MAX_BLOCKS_PER_DAY
                and day_minutes < MAX_DAILY_MINUTES
            ):
                block = remaining[0]

                duration = int(block["duration_minutes"])

                end = cursor + timedelta(minutes=duration)

                if end > slot_end:
                    break

                day_blocks.append({
                    "subject": block["subject"],
                    "task": block["task"],
                    "duration_minutes": duration,
                    "start": format_hhmm(cursor.hour, cursor.minute),
                    "end": format_hhmm(end.hour, end.minute),
                })

                day_minutes += duration
                remaining.pop(0)

                cursor = end + timedelta(minutes=BREAK_MINUTES)

        plan_days.append({
            "date": local_day.isoformat(),
            "blocks": day_blocks,
        })

        if not remaining:
            break

    return {
        "plan_title": "Study plan",
        "days": plan_days,
        "notes": "",
        "unscheduled": [
            block["task"] for block in remaining
        ],
    }


def _due_for(block, tasks):
    matched = _match_source_task(block.get("task", ""), tasks)

    return matched.get("due") if matched else None


# ---- Validation layer -------------------------------------------------

def validate_plan(plan, events, tz, tasks=None):
    """Deterministic checks over the assembled plan.

    Returns (ok, problems). Time values must be strict 24-hour
    HH:MM with minutes 00-59, ends must be after starts, sessions
    must not overlap, must not collide with calendar events, must
    respect breaks and daily limits, and unbacked tasks must be
    labelled as suggestions."""

    problems = []

    day_cursor = {}

    total_tasks = tasks or []

    for day in plan.get("days", []):
        previous_end = None
        day_minutes = 0

        for block in day.get("blocks", []):
            start = parse_hhmm(block.get("start"))
            end = parse_hhmm(block.get("end"))

            label = (
                f"{day.get('date')} "
                f"{block.get('subject')}: {block.get('task')}"
            )

            if start is None or end is None:
                problems.append(f"invalid time on {label}")

                continue

            start_minutes = start[0] * 60 + start[1]
            end_minutes = end[0] * 60 + end[1]

            if end_minutes <= start_minutes:
                problems.append(f"end before start on {label}")

            duration = block.get("duration_minutes")

            if (
                not isinstance(duration, int)
                or duration <= 0
                or duration != end_minutes - start_minutes
            ):
                problems.append(f"duration mismatch on {label}")

            elif duration > MAX_SESSION_MINUTES:
                problems.append(f"session too long on {label}")

            if previous_end is not None and start_minutes < previous_end:
                problems.append(f"overlapping sessions on {label}")

            if (
                previous_end is not None
                and 0 < start_minutes - previous_end < BREAK_MINUTES
            ):
                problems.append(f"missing break on {label}")

            day_minutes += end_minutes - start_minutes
            previous_end = end_minutes

            # Calendar conflict check against real busy intervals.
            local_date = day.get("date")

            try:
                block_day = date.fromisoformat(local_date)
            except (TypeError, ValueError):
                problems.append(f"invalid date {local_date}")

                continue

            for event_start, event_end in _event_intervals_utc(events):
                event_start = event_start.astimezone(tz)
                event_end = event_end.astimezone(tz)

                if event_start.date() != block_day:
                    continue

                event_start_minutes = (
                    event_start.hour * 60 + event_start.minute
                )
                event_end_minutes = (
                    event_end.hour * 60 + event_end.minute
                )

                if (
                    start_minutes < event_end_minutes
                    and event_start_minutes < end_minutes
                ):
                    problems.append(
                        f"conflicts with calendar event "
                        f"'{event_start}' on {label}"
                    )

            if total_tasks and _match_source_task(
                block.get("task", ""), total_tasks
            ) is None:
                # Unsupported claims are allowed only when clearly
                # labelled as suggestions.
                if not block.get("suggested"):
                    problems.append(
                        f"task not found in sources: {label}"
                    )

        if day_minutes > MAX_DAILY_MINUTES:
            problems.append(
                f"day {day.get('date')} exceeds daily limit"
            )

    return len(problems) == 0, problems


def repair_plan(plan, tasks, events, tz, days, start_date):
    """Rebuild the schedule from block metadata using the
    deterministic engine, then re-validate."""

    blocks = []

    for day in plan.get("days", []):
        for block in day.get("blocks", []):
            blocks.append({
                "subject": block.get("subject", "general"),
                "task": block.get("task", ""),
                "duration_minutes": block.get("duration_minutes") or 30,
                "priority": block.get("priority", 2),
            })

    if not blocks:
        return None

    rebuilt = _distribute(blocks, tasks, events, tz, days, start_date)
    rebuilt["plan_title"] = plan.get("plan_title", "Study plan")
    rebuilt["notes"] = plan.get("notes", "")

    ok, problems = validate_plan(rebuilt, events, tz, tasks)

    if not ok:
        return None

    return rebuilt


# ---- Model interaction -------------------------------------------------

def _extract_json(text):
    text = text.strip()

    fenced = re.search(
        r"```(?:json)?\s*(\{.*?\})\s*```",
        text,
        re.DOTALL,
    )

    if fenced:
        text = fenced.group(1)

    start = text.find("{")
    end = text.rfind("}")

    if start >= 0 and end > start:
        text = text[start:end + 1]

    return json.loads(text)


def _format_schedule_text(events, days, today):
    from backend.integrations.calendar.service import describe_schedule

    try:
        return describe_schedule(events, days=days)
    except Exception:
        return "Calendar information is not available."


def _format_tasks_text(tasks):
    if not tasks:
        return "No tasks found in the study groups."

    lines = []

    for task in tasks:
        due = f" (due {task['due']})" if task.get("due") else ""

        lines.append(
            f"- [{task['subject']}] {task['kind']}: "
            f"{task['title']}{due}"
        )

    return "\n".join(lines)


def _label_suggested(plan, tasks):
    for day in plan.get("days", []):
        for block in day.get("blocks", []):
            if _match_source_task(block.get("task", ""), tasks) is None:
                block["suggested"] = True

    return plan


async def build_study_plan(tasks, events=None, days=7):
    """Plan source-backed tasks inside real calendar free slots.

    tasks: normalized source-backed entries
        ({subject, kind, title, due}).
    events: calendar events ({title, start, end}, UTC ISO) used for
        busy-slot avoidance. Never modified.

    Returns {"plan": ..., "raw_plan": ...}. plan is None only when
    even the deterministic fallback could not be validated."""

    tz = datetime.now().astimezone().tzinfo
    today = datetime.now(tz).date()

    tasks = normalize_tasks(tasks)

    content = (
        "Task list from the study groups:\n"
        f"{_format_tasks_text(tasks)}\n\n"
        "Calendar (busy events and free slots, local time):\n"
        f"{_format_schedule_text(events or [], days, today)}\n\n"
        "Create the study plan."
    )

    answer = await provider_manager.ask(
        messages=[
            {"role": "system", "content": PLAN_INSTRUCTIONS},
            {"role": "user", "content": content},
        ],
    )

    model_plan = None
    raw_plan = None

    try:
        model_plan = _sanitize_model_blocks(
            _extract_json(answer),
            tasks,
        )
    except (json.JSONDecodeError, ValueError):
        raw_plan = answer

    if model_plan and not model_plan["blocks"]:
        model_plan = None
        raw_plan = raw_plan or answer

    blocks = (
        model_plan["blocks"]
        if model_plan
        else default_blocks(tasks, today)
    )

    plan = _distribute(blocks, tasks, events, tz, days, today)

    if model_plan:
        plan["plan_title"] = model_plan["plan_title"]
        plan["notes"] = model_plan["notes"]
    else:
        plan["notes"] = (
            "Generated from your group tasks directly because the "
            "planner model could not structure a plan."
        )

    plan = _label_suggested(plan, tasks)

    ok, problems = validate_plan(plan, events, tz, tasks)

    if not ok:
        rebuilt = repair_plan(
            plan, tasks, events, tz, days, today
        )

        if rebuilt is not None:
            plan = _label_suggested(rebuilt, tasks)
        else:
            return {
                "plan": None,
                "raw_plan": answer,
                "validation_problems": problems,
            }

    # Empty subjects are reported honestly instead of being filled
    # with generic templates.
    with_tasks = {task["subject"] for task in tasks}

    if with_tasks:
        plan["subjects_without_tasks"] = sorted(
            with_tasks.symmetric_difference(
                {
                    block["subject"]
                    for day in plan["days"]
                    for block in day["blocks"]
                }
                & with_tasks
            )
        )

    return {
        "plan": plan,
        "raw_plan": raw_plan,
    }
