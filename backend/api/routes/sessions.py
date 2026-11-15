
from fastapi import APIRouter, HTTPException

from backend.memory.database import (
    create_session,
    get_session,
    list_sessions,
    get_messages,
    close_session,
)

router = APIRouter(prefix="/api/sessions", tags=["Sessions"])


@router.post("/")
async def new_session():
    session_id = await create_session()
    return {"session_id": session_id}


@router.get("/")
async def sessions():
    return {"sessions": await list_sessions()}


@router.get("/{session_id}")
async def session_details(session_id: int):
    session = await get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    messages = await get_messages(session_id)

    return {
        "session": session,
        "messages": messages,
    }


@router.post("/{session_id}/close")
async def end_session(session_id: int):
    session = await get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    if session["closed_at"]:
        return {"success": True, "message": "Session already closed."}

    await close_session(session_id)

    return {"success": True, "message": "Session closed."}
