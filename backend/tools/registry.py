
from datetime import datetime, timezone
from pathlib import Path
import inspect
import platform
import re
import subprocess

from backend.core.config import settings
from backend.integrations.calendar import service as calendar_service
from backend.memory.database import (
    create_calendar_event,
    delete_calendar_event,
    get_event_by_id,
)
from starlette.concurrency import run_in_threadpool


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = PROJECT_ROOT / "data" / "workspace"
WORKSPACE.mkdir(parents=True, exist_ok=True)

MAX_WORKSPACE_READ_BYTES = 200_000


def get_time(arguments):
    return {
        "local_time": datetime.now().astimezone().isoformat()
    }


def _resolve_workspace_file(filename, extensions=(".txt",)):
    ext_pattern = "|".join(ext.lstrip(".") for ext in extensions)

    if not re.fullmatch(
        rf"[A-Za-z0-9_-]{{1,80}}\.(?:{ext_pattern})",
        filename,
    ):
        raise ValueError(
            "Invalid filename. Use a simple filename with extension "
            + ", ".join(extensions)
        )

    path = (WORKSPACE / filename).resolve()

    if path.parent != WORKSPACE.resolve():
        raise ValueError("File path is outside the Jarvis workspace.")

    return path


def create_note(arguments):
    filename = arguments.get("filename", "")
    content = arguments.get("content", "")

    if not isinstance(content, str) or not content.strip():
        raise ValueError("Note content cannot be empty.")

    if len(content) > 20000:
        raise ValueError("Note content is too long.")

    path = _resolve_workspace_file(filename, extensions=(".txt",))

    if path.exists():
        raise ValueError(
            f"A file named '{path.name}' already exists in the "
            "workspace. Jarvis never overwrites files; ask to delete "
            "it first or choose another filename."
        )

    path.write_text(content, encoding="utf-8")

    # Confirm success only after verifying the file exists on disk and
    # its contents match what was requested.
    if not path.is_file():
        raise OSError(
            f"File '{path.name}' reported as written but was not found "
            "on disk."
        )

    written = path.read_text(encoding="utf-8")

    if written != content:
        raise OSError(
            f"Verification failed: contents of '{path.name}' do not "
            "match the requested text."
        )

    return {
        "created": True,
        "verified": True,
        "filename": path.name,
        "location": str(path),
        "bytes": len(content.encode("utf-8")),
    }


def list_workspace_files(arguments):
    files = sorted(
        entry.name
        for entry in WORKSPACE.iterdir()
        if entry.is_file()
    )

    return {"files": files}


def read_workspace_file(arguments):
    path = _resolve_workspace_file(
        arguments.get("filename", ""),
        extensions=(".txt", ".md"),
    )

    if not path.is_file():
        raise ValueError("File not found in the Jarvis workspace.")

    data = path.read_bytes()

    if len(data) > MAX_WORKSPACE_READ_BYTES:
        raise ValueError("File is too large to read.")

    return {
        "filename": path.name,
        "content": data.decode("utf-8", errors="replace"),
    }


def system_info(arguments):
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
    }


def open_application(arguments):
    name = str(arguments.get("name", "")).strip().lower()

    command = settings.desktop_allowed_apps.get(name)

    if not command:
        raise ValueError(
            f"Application '{name}' is not in the allowed list."
        )

    subprocess.Popen(
        command,
        shell=True,
        cwd=str(PROJECT_ROOT),
    )

    return {
        "launched": name,
        "command": command,
    }


def _parse_datetime_argument(value):
    text = str(value).strip()

    if not text:
        raise ValueError("Missing datetime value.")

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise ValueError(
            "Use an ISO datetime like 2026-11-25T14:00 or "
            "2026-11-25T14:00+02:00."
        ) from error

    if parsed.tzinfo is None:
        parsed = parsed.astimezone()

    return parsed.astimezone(timezone.utc).isoformat()


async def read_calendar(arguments):
    try:
        days = int(arguments.get("days", 14))
    except (TypeError, ValueError):
        days = 14

    days = max(1, min(days, 60))

    events = await calendar_service.get_upcoming(days=days)

    return {"days": days, "events": events}


async def create_event(arguments):
    title = str(arguments.get("title", "")).strip()
    notes = arguments.get("notes")

    start_utc = _parse_datetime_argument(arguments.get("start", ""))
    end_utc = _parse_datetime_argument(arguments.get("end", ""))

    if not title:
        raise ValueError("Event title cannot be empty.")

    if len(title) > 200:
        raise ValueError("Event title is too long.")

    if start_utc >= end_utc:
        raise ValueError("Event start must be before its end.")

    event_id = await create_calendar_event(
        title,
        start_utc,
        end_utc,
        str(notes) if notes else None,
    )

    return {
        "created": True,
        "event_id": event_id,
        "title": title,
        "start_utc": start_utc,
        "end_utc": end_utc,
    }


async def delete_event(arguments):
    try:
        event_id = int(arguments.get("event_id"))
    except (TypeError, ValueError) as error:
        raise ValueError(
            "delete_event needs the numeric event_id shown by "
            "read_calendar."
        ) from error

    existing = await get_event_by_id(event_id)

    if not existing:
        raise ValueError(
            f"No local event with id {event_id}. Only events created "
            "locally can be deleted."
        )

    await delete_calendar_event(event_id)

    return {
        "deleted": True,
        "event_id": event_id,
        "title": existing["title"],
    }


async def telegram_digest(arguments):
    from backend.integrations.telegram.digest import build_digest

    try:
        hours = int(arguments.get("hours", 168))
    except (TypeError, ValueError):
        hours = 168

    hours = max(1, min(hours, 336))

    return await build_digest(hours=hours)


async def telegram_plan(arguments):
    from backend.integrations.telegram.report import build_study_report

    report = await build_study_report()

    return {"report": report}


TOOLS = {
    "get_time": {
        "description": "Get the computer's current local time.",
        "permission": "automatic",
        "function": get_time,
        "arguments": {},
    },
    "system_info": {
        "description": (
            "Get basic information about this computer "
            "(operating system, CPU architecture, Python version)."
        ),
        "permission": "automatic",
        "function": system_info,
        "arguments": {},
    },
    "list_workspace_files": {
        "description": (
            "List the note files stored in Jarvis's workspace."
        ),
        "permission": "automatic",
        "function": list_workspace_files,
        "arguments": {},
    },
    "read_workspace_file": {
        "description": (
            "Read the contents of a note in Jarvis's workspace."
        ),
        "permission": "automatic",
        "function": read_workspace_file,
        "arguments": {
            "filename": "note filename, e.g. ideas.txt",
        },
    },
    "create_note": {
        "description": "Create a text note in Jarvis's workspace.",
        "permission": "approval_required",
        "function": create_note,
        "arguments": {
            "filename": "simple .txt filename",
            "content": "note text",
        },
    },
    "open_application": {
        "description": (
            "Open an allowed desktop application, such as notepad, "
            "calculator, or paint."
        ),
        "permission": "approval_required",
        "function": open_application,
        "arguments": {
            "name": "application name from the allowed list",
        },
    },
    "read_calendar": {
        "description": (
            "Read Jarvis's upcoming calendar events (merged from the "
            "configured ICS calendar and locally created events) with "
            "busy and free time information."
        ),
        "permission": "automatic",
        "function": read_calendar,
        "arguments": {
            "days": "how many days ahead to look, 1-60 (default 14)",
        },
    },
    "create_event": {
        "description": (
            "Create a local calendar event. Only call this when the "
            "user explicitly asks to schedule something."
        ),
        "permission": "approval_required",
        "function": create_event,
        "arguments": {
            "title": "short event title",
            "start": "start datetime, e.g. 2026-11-25T14:00",
            "end": "end datetime, e.g. 2026-11-25T15:00",
            "notes": "optional notes",
        },
    },
    "delete_event": {
        "description": (
            "Delete a locally created calendar event by its event_id "
            "from read_calendar. Imported ICS events cannot be deleted."
        ),
        "permission": "approval_required",
        "function": delete_event,
        "arguments": {
            "event_id": "numeric id from read_calendar",
        },
    },
    "telegram_digest": {
        "description": (
            "Read recent messages from the user's Telegram study "
            "groups (Mathematics, Physics, Chemistry). The groups are "
            "already configured from .env; NEVER ask the user for "
            "group names. Strictly read-only: Jarvis never sends "
            "messages or modifies Telegram. Returns announcements, "
            "assignments, tests, lecture recordings and deadlines."
        ),
        "permission": "automatic",
        "function": telegram_digest,
        "arguments": {
            "hours": "how far back to read, 1-336 hours (default 168)",
        },
    },
    "telegram_plan": {
        "description": (
            "Read the Telegram study groups and build a suggested "
            "daily/weekly study plan from actual announcements, "
            "assignments and deadlines. Groups are pre-configured; "
            "never ask the user for group names. Suggestion only: it "
            "never creates or changes calendar events, and Telegram "
            "is never written to."
        ),
        "permission": "automatic",
        "function": telegram_plan,
        "arguments": {},
    },
}


def get_tool(name):
    return TOOLS.get(name)


def execute_tool(name, arguments):
    tool = get_tool(name)

    if not tool:
        raise ValueError(f"Tool '{name}' is not registered.")

    result = tool["function"](arguments)

    if inspect.iscoroutine(result):
        return result

    return result


async def run_tool(name, arguments):
    tool = get_tool(name)

    if not tool:
        raise ValueError(f"Tool '{name}' is not registered.")

    function = tool["function"]

    if inspect.iscoroutinefunction(function):
        return await function(arguments)

    return await run_in_threadpool(function, arguments)
