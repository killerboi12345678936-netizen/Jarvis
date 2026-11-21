
import json
import re

from backend.providers.manager import provider_manager


PLAN_INSTRUCTIONS = """You are Jarvis, a study planner. Given the student's
deadlines, assignments, existing calendar events and free time slots,
produce a realistic study plan.

Return ONLY a JSON object (no markdown fences):
{
  "plan_title": "...",
  "days": [
    {"date": "...", "blocks": [
      {"subject": "Mathematics", "task": "...", "duration_minutes": 60,
       "start": "HH:MM or null", "end": "HH:MM or null"}
    ]}
  ],
  "notes": "brief advice"
}

Rules:
- Study sessions of 45-90 minutes with realistic breaks between them.
- Prioritize the nearest deadlines.
- Respect the free time slots provided; do not schedule over busy events.
- Never invent deadlines or events that were not provided."""


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


async def build_study_plan(deadlines_text, schedule_text=""):
    content = (
        "Deadlines and assignments:\n"
        f"{deadlines_text or 'None provided.'}\n\n"
        "Existing calendar commitments and free slots:\n"
        f"{schedule_text or 'No calendar information provided.'}\n\n"
        "Create the study plan."
    )

    answer = await provider_manager.ask(
        messages=[
            {"role": "system", "content": PLAN_INSTRUCTIONS},
            {"role": "user", "content": content},
        ],
    )

    try:
        return {
            "plan": _extract_json(answer),
            "raw_plan": None,
        }

    except (json.JSONDecodeError, ValueError):
        return {
            "plan": None,
            "raw_plan": answer,
        }
