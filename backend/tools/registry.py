
from datetime import datetime
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = PROJECT_ROOT / "data" / "workspace"
WORKSPACE.mkdir(parents=True, exist_ok=True)


def get_time(arguments):
    return {
        "local_time": datetime.now().astimezone().isoformat()
    }


def create_note(arguments):
    filename = arguments.get("filename", "")
    content = arguments.get("content", "")

    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}\.txt", filename):
        raise ValueError("Invalid filename. Use a simple .txt filename.")

    if not isinstance(content, str) or not content.strip():
        raise ValueError("Note content cannot be empty.")

    if len(content) > 20000:
        raise ValueError("Note content is too long.")

    path = (WORKSPACE / filename).resolve()

    if path.parent != WORKSPACE.resolve():
        raise ValueError("File path is outside the Jarvis workspace.")

    if path.exists():
        raise ValueError("A note with this filename already exists.")

    path.write_text(content, encoding="utf-8")

    return {
        "created": True,
        "filename": filename,
        "location": str(path),
    }


TOOLS = {
    "get_time": {
        "description": "Get the computer's current local time.",
        "permission": "automatic",
        "function": get_time,
    },
    "create_note": {
        "description": "Create a text note in Jarvis's workspace.",
        "permission": "approval_required",
        "function": create_note,
    },
}


def get_tool(name):
    return TOOLS.get(name)


def execute_tool(name, arguments):
    tool = get_tool(name)

    if not tool:
        raise ValueError(f"Tool '{name}' is not registered.")

    return tool["function"](arguments)
