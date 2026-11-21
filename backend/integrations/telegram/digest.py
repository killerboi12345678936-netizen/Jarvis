
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
  "important": ["other important messages"],
  "summary": "2-3 sentence overall summary"
}

Rules:
- Only include items actually present in the messages; never invent deadlines.
- Keep quoted texts short. Preserve dates exactly as written.
- If there are no assignments or deadlines, use empty lists."""


PLAN_INSTRUCTIONS = """You are Jarvis, a study planner. Given the student's
deadlines, assignments and available time, produce a realistic study plan.

Return ONLY a JSON object (no markdown fences):
{
  "plan_title": "...",
  "days": [
    {"date": "...", "blocks": [
      {"subject": "Mathematics", "task": "...", "duration_minutes": 60}
    ]}
  ],
  "notes": "brief advice"
}

Rules:
- Sessions of 45-90 minutes with realistic breaks.
- Prioritize nearest deadlines.
- Never invent deadlines that were not provided."""


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


async def build_digest(hours=24):
    from backend.integrations.telegram.client import (
        fetch_recent_messages,
    )

    group_messages = await fetch_recent_messages(hours=hours)

    digest = {"hours": hours, "subjects": {}}

    for subject, group_data in group_messages.items():
        if not group_data.get("configured") or group_data.get("error"):
            digest["subjects"][subject] = {
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
                "messages_read": messages_read,
                "data": {
                    "announcements": [],
                    "assignments": [],
                    "deadlines": [],
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
            "messages_read": messages_read,
            "data": data,
            "raw_summary": raw,
        }

    return digest


async def build_study_plan(kind, days=7, deadlines_text=""):
    horizon = "daily (today only)" if kind == "daily" else f"weekly ({days} days)"

    content = (
        f"Plan horizon: {horizon}.\n"
        f"Today: the user will tell you the date context if needed.\n\n"
        f"Deadlines and assignments:\n{deadlines_text or 'None provided.'}\n\n"
        "Create the study plan."
    )

    data, raw = await _ask_json(PLAN_INSTRUCTIONS, content)

    return {"kind": kind, "plan": data, "raw_plan": raw}
