
import json

from backend.tools.permissions import propose_action
from backend.tools.registry import TOOLS, get_tool, run_tool


async def process_tool_calls(tool_calls):
    """Execute automatic tools and propose approval-required ones.

    Returns (follow_up_parts, pending_actions, tool_results).
    """

    follow_up_parts = []
    pending_actions = []
    tool_results = []

    for name, arguments in tool_calls:
        tool = get_tool(name)

        if not tool:
            error = (
                f"Unknown tool '{name}'. "
                f"Valid tools: {', '.join(sorted(TOOLS))}."
            )

            tool_results.append({
                "tool": name,
                "arguments": arguments,
                "error": error,
            })

            # Report the failure back to the model so it can retry
            # with a registered tool; without a follow-up part the
            # turn would end silently.
            follow_up_parts.append(
                f"TOOL_RESULT {name}: failed - {error}"
            )

            continue

        if tool["permission"] == "automatic":
            try:
                result = await run_tool(name, arguments)

                tool_results.append({
                    "tool": name,
                    "arguments": arguments,
                    "result": result,
                })

                follow_up_parts.append(
                    f"TOOL_RESULT {name}: "
                    f"{json.dumps(result, default=str)}"
                )

            except Exception as error:
                tool_results.append({
                    "tool": name,
                    "arguments": arguments,
                    "error": str(error),
                })

                follow_up_parts.append(
                    f"TOOL_RESULT {name}: failed - {error}"
                )

        else:
            action_id = await propose_action(name, arguments)

            pending_actions.append({
                "action_id": action_id,
                "tool": name,
                "arguments": arguments,
                "description": tool["description"],
            })

    return follow_up_parts, pending_actions, tool_results
