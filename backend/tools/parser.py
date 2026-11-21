
import json
import re

from backend.tools.registry import TOOLS


TOOL_OPEN_RE = re.compile(r"<{1,2}TOOL:")

TOOL_OPEN = "<<TOOL:"

TOOL_CLOSE = ">>"


class ToolStreamFilter:
    """Extracts <<TOOL:{...}>> blocks from streamed model output.

    Small models sometimes emit single-bracket markers (<TOOL:{...}>)
    or a bare tool name (<<TOOL:get_time>>), so the parser accepts
    those variants. Text safe to display or speak is returned from
    feed()/finish(); complete tool calls are collected in tool_calls.
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
                    emitted.append(self.buffer)
                    self.buffer = ""
                else:
                    self.buffer = self.buffer[opener.start():]

                break

            raw_block = self.buffer[opener.start():close + 1]

            body = self.buffer[body_start:close]

            if not self._register(body):
                self.invalid_blocks.append(body)
                emitted.append(raw_block)

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

            try:
                json.loads(candidate.strip())
            except (json.JSONDecodeError, ValueError):
                continue

            return position

        if final and positions:
            return min(positions)

        return None

    def _register(self, block):
        try:
            data = json.loads(block.strip())

            name = data.get("name")
            arguments = data.get("arguments", {})

            if isinstance(name, str) and isinstance(arguments, dict):
                self.tool_calls.append((name, arguments))
                return True

        except (json.JSONDecodeError, ValueError):
            pass

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
        "Only use tools from the list below. After emitting a tool call,",
        "stop and wait for the result. Do not invent tools or results.",
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
