
import ast
import json
import re

from backend.tools.registry import TOOLS


TOOL_OPEN_RE = re.compile(r"<{1,2}TOOL:")

TOOL_OPEN = "<<TOOL:"

TOOL_CLOSE = ">>"

# Bare Python-style literals after a colon (models emit
# "arguments": none instead of null). Only applied when strict JSON
# parsing fails; the quote at the start of a string value prevents
# matches inside quoted text.
BARE_LITERAL_RE = re.compile(r"(:\s*)(none|None|True|False)\b")

HTML_BREAK_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)

# Real proposal notes are appended by the backend after the model
# finishes. If this text shows up in the model's OWN output, no tool
# call was emitted and the model fabricated the note by copying chat
# history (small models do this).
FAKE_PROPOSAL_RE = re.compile(
    r"\s*\[Action proposed[^\]]*\]"
    r"(?:\s*\.?\s*Open the Actions panel[^.]*\.?)?"
)

TOOL_CALL_CORRECTION = (
    "Your previous reply said an action was proposed, but you did "
    "not actually emit a tool call. If the user's request requires "
    "a tool, emit the call now in the exact format "
    '<<TOOL:{"name": "tool_name", "arguments": {}}>> on its own '
    "line, then stop. Do not describe or imitate proposal notes. If "
    "no tool is needed, answer normally."
)

MALFORMED_CALL_CORRECTION = (
    "Your previous reply contained a tool call that could not be "
    "parsed. Emit the call again, exactly in the format "
    '<<TOOL:{"name": "tool_name", "arguments": {}}>> on its own '
    "line, with valid JSON and no extra text or HTML on that line. "
    "Use {} for the arguments when the tool needs none. If no tool "
    "is needed, just answer normally."
)


def normalize_visible_text(text):
    """Model output sometimes contains HTML line-break tags that the
    chat UI would display literally; convert them to real newlines."""
    return HTML_BREAK_RE.sub("\n", text)


def strip_fake_proposals(text):
    """Remove proposal notes the model fabricated instead of emitting
    a real tool call."""
    return FAKE_PROPOSAL_RE.sub("", text)


def _jsonify_literal(match):
    word = match.group(2)

    if word.lower() == "none":
        return match.group(1) + "null"

    return match.group(1) + word.lower()


def _try_json_loads(text):
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _try_literal_eval(text):
    """Last resort for Python-style bodies such as
    {'name': 'get_time', 'arguments': {}}. ast.literal_eval never
    executes code, so model output is safe to evaluate."""

    if not text.startswith("{"):
        return None

    try:
        data = ast.literal_eval(text)
    except (ValueError, SyntaxError, TypeError, MemoryError):
        return None

    return data if isinstance(data, dict) else None


def parse_tool_json(text):
    """Parse a tool-call body, tolerating the malformed variants small
    models emit: a stray extra closing brace before >>, bare Python
    literals (none/None/True/False instead of JSON null/true/false),
    and Python dict syntax with single quotes."""

    stripped = text.strip()

    candidates = [stripped]

    if (
        stripped.endswith("}")
        and stripped.count("{") < stripped.count("}")
    ):
        candidates.append(stripped[:-1])

    for candidate in candidates:
        data = _try_json_loads(candidate)

        if data is not None:
            return data

        data = _try_json_loads(
            BARE_LITERAL_RE.sub(_jsonify_literal, candidate)
        )

        if data is not None:
            return data

        data = _try_literal_eval(candidate)

        if data is not None:
            return data

    return None


def normalize_tool_name(value):
    if not isinstance(value, str):
        return None

    name = value.strip().lower()

    return name or None


def normalize_arguments(value):
    """Missing, null-like or non-object argument payloads become an
    empty dict; each tool then validates its own required arguments
    and produces a clear error the model can retry from."""

    if isinstance(value, dict):
        return value

    if isinstance(value, str) and value.strip().lower() in (
        "",
        "none",
        "null",
        "{}",
    ):
        return {}

    return {}


class ToolStreamFilter:
    """Extracts <<TOOL:{...}>> blocks from streamed model output.

    Small models emit many variants (single-bracket markers,
    bare tool names, Python-style arguments, "arguments": none, a
    stray <br> after the call); the parser salvages them all. Bodies
    that cannot be salvaged are held out of the visible text and
    collected in invalid_blocks so the chat loop can give the model
    a corrective round instead of showing raw markup to the user.
    Tool names are not validated here: unknown names are still
    registered (and hidden) so the dispatcher can report them back
    to the model for a retry.
    """

    def __init__(self):
        self.buffer = ""
        self.tool_calls = []
        self.invalid_blocks = []

    def feed(self, chunk):
        self.buffer += chunk
        return self._drain(final=False)

    def finish(self):
        return self._drain(final=True)

    def _drain(self, final):
        emitted = []

        while True:
            opener = TOOL_OPEN_RE.search(self.buffer)

            if not opener:
                if final:
                    emitted.append(self.buffer)
                    self.buffer = ""
                else:
                    holdback = self._holdback_length()

                    if holdback < len(self.buffer):
                        split = len(self.buffer) - holdback

                        emitted.append(self.buffer[:split])
                        self.buffer = self.buffer[split:]

                break

            emitted.append(self.buffer[:opener.start()])

            body_start = opener.end()

            close = self._find_close(body_start, final)

            # A close sitting at the very end of a still-running stream
            # may be the first half of ">>"; wait for one more chunk.
            if (
                close is not None
                and not final
                and close == len(self.buffer) - 1
                and self.buffer[close:close + 2] != TOOL_CLOSE
            ):
                close = None

            if close is None:
                if final:
                    # The model may end its turn without ever closing
                    # the marker; salvage the call when the body is
                    # otherwise complete.
                    candidate = self.buffer[body_start:]

                    if not self._register(candidate):
                        self.invalid_blocks.append(candidate)

                    self.buffer = ""
                else:
                    self.buffer = self.buffer[opener.start():]

                break

            body = self.buffer[body_start:close]

            if not self._register(body):
                self.invalid_blocks.append(body)

            close_length = (
                2
                if self.buffer[close:close + 2] == TOOL_CLOSE
                else 1
            )

            self.buffer = self.buffer[close + close_length:]

        return "".join(emitted)

    def _holdback_length(self):
        """Longest buffer suffix that could still grow into a marker
        opener; both <<TOOL: and <TOOL: must stay in the buffer."""

        for length in range(
            min(len(self.buffer), len(TOOL_OPEN)), 0, -1
        ):
            suffix = self.buffer[-length:]

            if (
                TOOL_OPEN.startswith(suffix)
                or TOOL_OPEN[1:].startswith(suffix)
            ):
                return length

        return 0

    def _find_close(self, body_start, final):
        """Find the marker close, tolerating > or >> and JSON-internal
        > characters by trying successive > positions. While the stream
        is still running, only an already-parseable close counts; a
        fallback close is chosen only once the stream ends."""

        positions = set()

        double = self.buffer.find(TOOL_CLOSE, body_start)

        if double >= 0:
            positions.add(double)

        search_from = body_start

        while True:
            single = self.buffer.find(">", search_from)

            if single < 0:
                break

            positions.add(single)
            search_from = single + 1

        for position in sorted(positions):
            candidate = self.buffer[body_start:position]

            if parse_tool_json(candidate) is not None:
                return position

        if final and positions:
            return min(positions)

        return None

    def _register(self, block):
        data = parse_tool_json(block)

        if isinstance(data, dict):
            name = normalize_tool_name(data.get("name"))

            if name:
                self.tool_calls.append(
                    (name, normalize_arguments(data.get("arguments")))
                )
                return True

        bare_name = block.strip().lower()

        if bare_name in TOOLS and not TOOLS[bare_name]["arguments"]:
            self.tool_calls.append((bare_name, {}))
            return True

        return False


def build_tool_prompt():
    lines = [
        "You can use tools. When a tool would help, emit exactly this",
        "format on its own line (and nothing else on that line):",
        '<<TOOL:{"name": "tool_name", "arguments": {"arg": "value"}}>>',
        "Use double angle brackets << >> exactly as shown.",
        "If a tool takes no arguments, pass an empty object {} exactly:",
        '<<TOOL:{"name": "tool_name", "arguments": {}}>>.',
        "Never write none or null for the arguments and never omit the",
        "arguments field. Never wrap a tool call in HTML such as <br>.",
        "You may emit several tool calls, each on its own line.",
        "Only use tools from the list below. After emitting a tool call,",
        "stop and wait for the result. Do not invent tools or results.",
        "",
        "Arguments must match the user's request EXACTLY. Use the same",
        "filename, spelling, capitalization and text the user gave;",
        "never rename, translate, shorten or rephrase requested names",
        "or content. If the user asks for 'Jarvis.txt' use 'Jarvis.txt'.",
        "When a tool needs approval, just emit the call; the system",
        "shows the proposal to the user.",
        "",
        "Available tools:",
    ]

    for name, tool in TOOLS.items():
        args = ", ".join(tool["arguments"].keys()) or "none"
        permission_note = (
            "(runs automatically)"
            if tool["permission"] == "automatic"
            else "(requires user approval)"
        )

        lines.append(
            f"- {name} {permission_note}: {tool['description']} "
            f"[arguments: {args}]"
        )

    return "\n".join(lines)
