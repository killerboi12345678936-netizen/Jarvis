
import json
import re

from backend.providers.manager import provider_manager, ProviderError


DIGEST_INSTRUCTIONS = """You are Jarvis, a study assistant. Below are recent
messages from a study group. Classify them.

Return ONLY a JSON object with this exact shape (no markdown fences, no
commentary):
{
  "announcements": ["short announcement texts"],
  "assignments": [{"title": "...", "details": "...", "deadline": "date text or null"}],
  "deadlines": [{"what": "...", "when": "date text or null"}],
  "recordings": ["lecture or class recording links or messages"],
  "important": ["other important messages"],
  "summary": "2-3 sentence overall summary"
}

Rules:
- Only include items actually present in the messages; never invent deadlines.
- Put lecture recording or class-recording links under recordings.
- Keep quoted texts short. Preserve dates exactly as written.
- If there are no assignments or deadlines, use empty lists."""


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


async def _ask_json(instructions, content):
    answer = await provider_manager.ask(
        messages=[
            {"role": "system", "content": instructions},
            {"role": "user", "content": content},
        ],
    )

    try:
        return _extract_json(answer), None
    except (json.JSONDecodeError, ValueError):
        return None, answer


def _format_messages(subject, group_data):
    lines = [f"SUBJECT: {subject}"]

    if group_data.get("title"):
        lines.append(f"GROUP: {group_data['title']}")

    for message in group_data.get("messages", []):
        if not message.get("text"):
            continue

        sender = message.get("sender") or "unknown"
        date = message.get("date", "")[:16].replace("T", " ")

        text = message["text"][:500]

        lines.append(f"[{date}] {sender}: {text}")

    return "\n".join(lines)


def _as_list(value):
    if isinstance(value, list):
        return value

    # A drifted scalar still carries content; keep it instead of
    # silently dropping the only entry the model produced.
    if value is None or value == "":
        return []

    return [value]


def _as_text(value):
    if isinstance(value, str):
        return value

    if value is None:
        return None

    return json.dumps(value, ensure_ascii=False)


def normalize_digest_data(data):
    """Small models sometimes drift from the requested JSON shape
    (deadline strings instead of {what, when} objects, string
    assignments, missing keys); coerce everything into the canonical
    shape the UI and plan builder rely on."""

    if not isinstance(data, dict):
        data = {}

    assignments = []

    for item in _as_list(data.get("assignments")):
        if isinstance(item, dict):
            assignments.append({
                "title": _as_text(item.get("title")) or "",
                "details": _as_text(item.get("details")),
                "deadline": _as_text(item.get("deadline")),
            })
        else:
            assignments.append({
                "title": _as_text(item) or "",
                "details": None,
                "deadline": None,
            })

    deadlines = []

    for item in _as_list(data.get("deadlines")):
        if isinstance(item, dict):
            deadlines.append({
                "what": _as_text(item.get("what")) or "",
                "when": _as_text(item.get("when")),
            })
        else:
            deadlines.append({
                "what": _as_text(item) or "",
                "when": None,
            })

    return {
        "announcements": [
            text for text in (
                _as_text(item)
                for item in _as_list(data.get("announcements"))
            )
            if text
        ],
        "assignments": assignments,
        "deadlines": deadlines,
        "recordings": [
            text for text in (
                _as_text(item)
                for item in _as_list(data.get("recordings"))
            )
            if text
        ],
        "important": [
            text for text in (
                _as_text(item)
                for item in _as_list(data.get("important"))
            )
            if text
        ],
        "summary": _as_text(data.get("summary")) or "",
    }


def collect_deadlines(digest):
    """Flatten digest assignments and deadlines into planner input."""

    lines = []

    for subject, subject_data in digest.get("subjects", {}).items():
        data = subject_data.get("data")

        if not data:
            continue

        for deadline in data.get("deadlines", []):
            lines.append(
                f"- [{subject}] {deadline.get('what', '')} - "
                f"due {deadline.get('when') or 'unknown'}"
            )

        for assignment in data.get("assignments", []):
            lines.append(
                f"- [{subject}] assignment: "
                f"{assignment.get('title', '')} - "
                f"due {assignment.get('deadline') or 'unknown'}"
            )

    return "\n".join(lines)


TEST_TITLE_RE = re.compile(r"\b(test|exam|quiz|paper)\b", re.IGNORECASE)


def collect_tasks(digest):
    """Structured, source-backed task inventory for the planner.

    Every entry quotes an actual message item; nothing is invented
    here, and subjects with no messages produce no entries."""

    tasks = []

    for subject, subject_data in digest.get("subjects", {}).items():
        data = subject_data.get("data")

        if not data:
            continue

        for assignment in data.get("assignments", []):
            title = (assignment.get("title") or "").strip()

            if not title:
                continue

            tasks.append({
                "subject": subject,
                "kind": (
                    "test" if TEST_TITLE_RE.search(title)
                    else "assignment"
                ),
                "title": title,
                "due": assignment.get("deadline"),
            })

        for deadline in data.get("deadlines", []):
            what = (deadline.get("what") or "").strip()

            if not what:
                continue

            tasks.append({
                "subject": subject,
                "kind": (
                    "test" if TEST_TITLE_RE.search(what)
                    else "deadline"
                ),
                "title": what,
                "due": deadline.get("when"),
            })

        for recording in data.get("recordings", []):
            text = (recording or "").strip()

            if not text:
                continue

            tasks.append({
                "subject": subject,
                "kind": "recording",
                "title": text,
                "due": None,
            })

    return tasks


async def build_digest(hours=24):
    from backend.integrations.telegram.client import (
        fetch_recent_messages,
    )

    group_messages = await fetch_recent_messages(hours=hours)

    digest = {"hours": hours, "subjects": {}}

    for subject, group_data in group_messages.items():
        if not group_data.get("configured") or group_data.get("error"):
            digest["subjects"][subject] = {
                "title": group_data.get("title"),
                "messages_read": 0,
                "error": group_data.get("error"),
                "data": None,
            }

            continue

        messages_read = len(group_data.get("messages", []))

        if not any(
            message.get("text")
            for message in group_data.get("messages", [])
        ):
            digest["subjects"][subject] = {
                "title": group_data.get("title"),
                "messages_read": messages_read,
                "data": {
                    "announcements": [],
                    "assignments": [],
                    "deadlines": [],
                    "recordings": [],
                    "important": [],
                    "summary": "No text messages in this period.",
                },
            }

            continue

        data, raw = await _ask_json(
            DIGEST_INSTRUCTIONS,
            _format_messages(subject, group_data),
        )

        digest["subjects"][subject] = {
            "title": group_data.get("title"),
            "messages_read": messages_read,
            "data": normalize_digest_data(data) if data else None,
            "raw_summary": raw,
        }

    return digest
