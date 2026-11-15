
import json
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.tools.registry import (
    TOOLS,
    execute_tool,
    get_tool,
)
from backend.tools.permissions import (
    propose_action,
    get_action,
    list_actions,
    update_action,
    claim_action,
    finish_action,
)

router = APIRouter(prefix="/api/actions", tags=["Agent Actions"])


class ActionRequest(BaseModel):
    tool_name: str
    arguments: dict = Field(default_factory=dict)


@router.get("/tools")
async def available_tools():
    return {
        name: {
            "description": tool["description"],
            "permission": tool["permission"],
        }
        for name, tool in TOOLS.items()
    }


@router.post("/propose")
async def propose(request: ActionRequest):
    tool = get_tool(request.tool_name)

    if not tool:
        raise HTTPException(status_code=404, detail="Unknown tool.")

    if tool["permission"] == "automatic":
        try:
            result = execute_tool(
                request.tool_name,
                request.arguments,
            )
            return {
                "status": "completed",
                "result": result,
            }
        except (ValueError, OSError) as error:
            raise HTTPException(
                status_code=400,
                detail=str(error),
            ) from error

    action_id = await propose_action(
        request.tool_name,
        request.arguments,
    )

    return {
        "action_id": action_id,
        "status": "pending",
        "message": "This action requires your approval.",
    }


@router.get("/")
async def actions(status: Literal[
    "pending", "executing", "approved", "rejected", "failed"
] | None = None):
    return {"actions": await list_actions(status)}


@router.post("/{action_id}/approve")
async def approve(action_id: int):
    action = await get_action(action_id)

    if not action:
        raise HTTPException(status_code=404, detail="Action not found.")

    if action["status"] != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Action is already {action['status']}.",
        )

    if not await claim_action(action_id):
        raise HTTPException(
            status_code=409,
            detail="Action could not be claimed.",
        )

    try:
        arguments = json.loads(action["arguments"])

        result = execute_tool(
            action["tool_name"],
            arguments,
        )

        await finish_action(
            action_id,
            "approved",
            json.dumps(result),
        )

        return {
            "success": True,
            "status": "approved",
            "result": result,
        }

    except Exception as error:
        await finish_action(
            action_id,
            "failed",
            str(error),
        )

        raise HTTPException(
            status_code=400,
            detail=f"Action failed: {error}",
        ) from error


@router.post("/{action_id}/reject")
async def reject(action_id: int):
    success = await update_action(
        action_id,
        "rejected",
        "Rejected by user.",
    )

    if not success:
        raise HTTPException(
            status_code=409,
            detail="Action not found or no longer pending.",
        )

    return {
        "success": True,
        "status": "rejected",
    }
