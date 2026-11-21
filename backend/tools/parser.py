
import json

from backend.tools.registry import TOOLS


TOOL_OPEN = "<<TOOL:"

TOOL_CLOSE = ">>"


class ToolStreamFilter:
    """Extracts <<TOOL:{...}>> blocks from streamed model output.

    Text safe to display or speak is returned from feed()/finish();
    complete tool calls are collected in tool_calls.
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
            start = self.buffer.find(TOOL_OPEN)

            if start < 0:
                if final:
                    emitted.append(self.buffer)
                    self.buffer = ""
                else:
                    keep = len(self.buffer) - len(TOOL_OPEN) + 1

                    if keep > 0:
                        emitted.append(self.buffer[:keep])
                        self.buffer = self.buffer[keep:]

                break

            emitted.append(self.buffer[:start])

            end = self.buffer.find(TOOL_CLOSE, start)

            if end < 0:
                if final:
                    emitted.append(self.buffer)
                    self.buffer = ""
                else:
                    self.buffer = self.buffer[start:]

                break

            self._register(
                self.buffer[start + len(TOOL_OPEN):end],
            )

            self.buffer = self.buffer[end + len(TOOL_CLOSE):]

        return "".join(emitted)

    def _register(self, block):
        try:
            data = json.loads(block.strip())

            name = data.get("name")
            arguments = data.get("arguments", {})

            if isinstance(name, str) and isinstance(arguments, dict):
                self.tool_calls.append((name, arguments))
                return

        except json.JSONDecodeError:
            pass

        self.invalid_blocks.append(block)


def build_tool_prompt():
    lines = [
        "You can use tools. When a tool would help, emit exactly this",
        "format on its own line (and nothing else on that line):",
        '<<TOOL:{"name": "tool_name", "arguments": {"arg": "value"}}>>',
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
