
from datetime import datetime
from pathlib import Path
import platform
import re
import subprocess

from backend.core.config import settings


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
        raise ValueError("A note with this filename already exists.")

    path.write_text(content, encoding="utf-8")

    return {
        "created": True,
        "filename": filename,
        "location": str(path),
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
}


def get_tool(name):
    return TOOLS.get(name)


def execute_tool(name, arguments):
    tool = get_tool(name)

    if not tool:
        raise ValueError(f"Tool '{name}' is not registered.")

    return tool["function"](arguments)
