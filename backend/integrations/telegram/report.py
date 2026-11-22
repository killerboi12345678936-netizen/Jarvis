
import logging
import re

logger = logging.getLogger(__name__)

SUBJECT_ORDER = ("mathematics", "physics", "chemistry")

READONLY_NOTE = (
    "Read-only: I never send messages to or modify anything in Telegram."
)

NOT_CONFIGURED_NOTICE = (
    "Your Telegram study groups are not configured yet. Add "
    "TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION and the "
    "TELEGRAM_GROUP_* variables to .env, then restart Jarvis."
)

WORKFLOW_ERROR_NOTICE = (
    "I could not read your Telegram study groups just now. Please "
    "try again in a moment. " + READONLY_NOTE
)

# ---- Intent routing -------------------------------------------------

STUDY_SUBJECT_RE = re.compile(
    r"\b(mathematics|maths|math|physics|physic|chemistry|chemist)\b",
    re.IGNORECASE,
)

STUDY_TOPIC_RE = re.compile(
    r"\b(announcements?|assignments?|homework|tests?|exams?|quiz|"
    r"quizzes|lectures?|recordings?|deadlines?|digest|summari\w*|"
    r"organi\w*|study plan)\b",
    re.IGNORECASE,
)

GROUP_CONTEXT_RE = re.compile(
    r"\b(telegram|study groups?|groups?)\b",
    re.IGNORECASE,
)

PLAN_PHRASE_RE = re.compile(
    r"\b(study plan|daily plan|weekly plan|plan (?:for|my) "
    r"(?:today|tomorrow|this week|the week))\b",
    re.IGNORECASE,
)


def _subject_hits(text):
    hits = set()

    for match in STUDY_SUBJECT_RE.finditer(text):
        word = match.group(0).lower()

        if word.startswith("math"):
            hits.add("mathematics")
        elif word.startswith("physic"):
            hits.add("physics")
        else:
            hits.add("chemistry")

    return hits


def match_study_intent(text):
    """True when the message asks about study-group content.

    Deterministic so requests like "read my group announcements and
    plan my week" route to the Telegram workflow even when the small
    chat model fails to pick a tool."""
    if not text or not STUDY_TOPIC_RE.search(text):
        return False

    if GROUP_CONTEXT_RE.search(text):
        return True

    if PLAN_PHRASE_RE.search(text):
        return True

    # Asking about deadlines/assignments across multiple subjects is
    # study-group content even without the word "plan" or "group".
    return len(_subject_hits(text)) >= 2


# ---- Report formatting ----------------------------------------------

def _format_subject_section(subject, subject_data):
    label = subject.upper()
    title = subject_data.get("title")
    heading = f"{label}" + (f" — {title}" if title else "")

    if subject_data.get("error"):
        return f"{heading}\nCould not read this group: {subject_data['error']}"

    data = subject_data.get("data")

    if not data:
        return f"{heading}\nNo data available for this group."

    count = subject_data.get("messages_read", 0)

    lines = [f"{heading} ({count} messages)"]

    if count == 0:
        lines.append("No messages in this period.")

    if data.get("assignments"):
        lines.append("Assignments:")
        for assignment in data["assignments"]:
            due = assignment.get("deadline") or "no stated deadline"
            lines.append(f"- {assignment.get('title', '')} (due {due})")

    if data.get("deadlines"):
        lines.append("Deadlines:")
        for deadline in data["deadlines"]:
            when = deadline.get("when") or "unspecified"
            lines.append(f"- {deadline.get('what', '')} ({when})")

    if data.get("recordings"):
        lines.append("Lecture recordings:")
        for recording in data["recordings"]:
            lines.append(f"- {recording}")

    if data.get("announcements"):
        lines.append("Announcements:")
        for announcement in data["announcements"]:
            lines.append(f"- {announcement}")

    if data.get("important"):
        lines.append("Other important messages:")
        for item in data["important"]:
            lines.append(f"- {item}")

    if data.get("summary"):
        lines.append(f"Summary: {data['summary']}")

    return "\n".join(lines)


def format_digest_report(digest):
    subjects = digest.get("subjects", {})
    hours = digest.get("hours", 168)

    lines = [
        "Here is the latest from your study groups "
        f"(last {max(1, hours // 24)} day(s)). {READONLY_NOTE}",
        "",
    ]

    empty_subjects = []

    for subject in SUBJECT_ORDER:
        subject_data = subjects.get(subject)

        if not subject_data:
            empty_subjects.append(subject)
            lines.append(f"{subject.upper()}: not configured.")
            lines.append("")
            continue

        if subject_data.get("messages_read", 0) == 0 and not subject_data.get(
            "error"
        ):
            empty_subjects.append(subject)

        lines.append(_format_subject_section(subject, subject_data))
        lines.append("")

    if empty_subjects:
        listed = ", ".join(s.upper() for s in empty_subjects)
        lines.append(
            f"Note: {listed} had no messages in this period, so nothing "
            "could be confirmed from them."
        )
        lines.append("")

    return "\n".join(lines).rstrip()


def format_plan_report(plan_result):
    plan = (plan_result or {}).get("plan")

    if not plan:
        raw = (plan_result or {}).get("raw_plan")

        if raw:
            return (
                "SUGGESTED STUDY PLAN (raw)\n"
                "I could not structure the plan cleanly; here is the "
                "planner output:\n" + str(raw)[:800]
            )

        return None

    lines = [
        "SUGGESTED STUDY PLAN — times and durations are suggestions "
        "only, computed from your real calendar free slots, and I "
        "have not created or changed any calendar events. Tasks come "
        "from your group messages; anything else is marked as a "
        "suggestion.",
        "",
    ]

    for day in plan.get("days", []) or []:
        date = day.get("date", "")
        lines.append(f"{date}:")

        for block in day.get("blocks", []) or []:
            start = block.get("start") or ""
            end = block.get("end") or ""
            duration = block.get("duration_minutes")
            clock = (
                f"{start}-{end} "
                if start and end
                else (
                    f"({duration} min) "
                    if duration
                    else ""
                )
            )
            subject = (block.get("subject") or "").capitalize()
            label = (
                " (suggestion — not from your groups)"
                if block.get("suggested")
                else ""
            )
            lines.append(
                f"- {clock}{subject}: {block.get('task', '')}{label}"
            )

        lines.append("")

    unscheduled = plan.get("unscheduled") or []

    if unscheduled:
        lines.append(
            "Not scheduled (no free time in the window): "
            + "; ".join(unscheduled)
        )
        lines.append("")

    subjects_without = plan.get("subjects_without_tasks") or []

    if subjects_without:
        lines.append(
            "No plan blocks for "
            + ", ".join(s.capitalize() for s in subjects_without)
            + ": their tasks did not fit the available free time."
        )
        lines.append("")

    if plan.get("notes"):
        lines.append(f"Notes: {plan['notes']}")

    return "\n".join(lines).rstrip()


# ---- Workflow --------------------------------------------------------

async def build_study_report(hours=168, plan_days=7):
    """Digest + plan workflow behind the deterministic intent route."""

    from backend.integrations.calendar import service as calendar_service
    from backend.integrations.planning import build_study_plan
    from backend.integrations.telegram.digest import (
        build_digest,
        collect_tasks,
    )

    digest = await build_digest(hours=hours)

    sections = [format_digest_report(digest)]

    tasks = collect_tasks(digest)

    if tasks:
        try:
            events = await calendar_service.get_upcoming(
                days=plan_days
            )
        except Exception:
            logger.warning(
                "Calendar unavailable; planning without busy events.",
                exc_info=True,
            )
            events = None

        try:
            plan_result = await build_study_plan(
                tasks=tasks,
                events=events,
                days=plan_days,
            )
        except Exception:
            logger.warning(
                "Study plan generation failed; reporting digest only.",
                exc_info=True,
            )
            plan_result = None

        plan_section = format_plan_report(plan_result)

        if plan_section:
            sections.append(plan_section)
    else:
        sections.append(
            "No assignments, tests or deadlines were found in the "
            "messages, so there is nothing to plan around yet. If "
            "information is missing above, say so in the group or "
            "ask me again later — I will not invent tasks."
        )

    return "\n\n".join(sections)


async def build_study_report_safe(hours=168):
    """Never raises: returns report text or an honest notice."""

    from backend.integrations.telegram.client import TelegramNotConfigured

    try:
        return await build_study_report(hours=hours)
    except TelegramNotConfigured:
        return NOT_CONFIGURED_NOTICE
    except Exception:
        logger.exception("Study-group report workflow failed.")
        return WORKFLOW_ERROR_NOTICE
