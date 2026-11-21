
import json

from starlette.concurrency import run_in_threadpool

from backend.tools.permissions import propose_action
from backend.tools.registry import execute_tool, get_tool


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
            tool_results.append({
                "tool": name,
                "arguments": arguments,
                "error": "Unknown tool.",
            })
            continue

        if tool["permission"] == "automatic":
            try:
                result = await run_in_threadpool(
                    execute_tool,
                    name,
                    arguments,
                )

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
