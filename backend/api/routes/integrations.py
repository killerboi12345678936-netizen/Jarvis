
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.core.config import settings
from backend.integrations.calendar import service as calendar_service
from backend.integrations.telegram import client as telegram_client
from backend.integrations.telegram import digest as telegram_digest
from backend.providers.manager import ProviderError


router = APIRouter(
    prefix="/api/integrations",
    tags=["Integrations"],
)


class CalendarEventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    start: str = Field(min_length=1, max_length=40)
    end: str = Field(min_length=1, max_length=40)
    notes: str | None = Field(default=None, max_length=2000)


class CalendarEventUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    start: str | None = Field(default=None, min_length=1, max_length=40)
    end: str | None = Field(default=None, min_length=1, max_length=40)
    notes: str | None = Field(default=None, max_length=2000)


def _handle_telegram_error(error):
    if isinstance(error, telegram_client.TelegramNotConfigured):
        raise HTTPException(
            status_code=503,
            detail=str(error),
        ) from error

    raise HTTPException(
        status_code=502,
        detail=f"Telegram error: {error}",
    ) from error


@router.get("/telegram/status")
async def telegram_status():
    status = telegram_client.status()

    connected = False

    if status["credentials_present"]:
        try:
            await telegram_client.ensure_connected()

            connected = True

        except Exception:
            connected = False

    return {**status, "connected": connected}


@router.get("/telegram/digest")
async def telegram_digest_route(
    hours: int = Query(default=24, ge=1, le=168),
):
    try:
        return await telegram_digest.build_digest(hours=hours)

    except ProviderError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error

    except Exception as error:
        _handle_telegram_error(error)


@router.get("/telegram/plan")
async def telegram_plan_route(
    kind: str = Query(default="weekly", pattern="^(daily|weekly)$"),
    days: int = Query(default=7, ge=1, le=14),
    hours: int = Query(default=168, ge=1, le=336),
):
    try:
        digest = await telegram_digest.build_digest(hours=hours)

        deadlines_text = ""

        for subject, subject_data in digest["subjects"].items():
            data = subject_data.get("data")

            if not data:
                continue

            for deadline in data.get("deadlines", []):
                deadlines_text += (
                    f"- [{subject}] {deadline.get('what', '')} - "
                    f"due {deadline.get('when', 'unknown')}\n"
                )

            for assignment in data.get("assignments", []):
                deadlines_text += (
                    f"- [{subject}] assignment: "
                    f"{assignment.get('title', '')} - "
                    f"due {assignment.get('deadline') or 'unknown'}\n"
                )

        from backend.integrations.planning import build_study_plan

        plan = await build_study_plan(deadlines_text=deadlines_text)

        return {
            "kind": kind,
            "days": days,
            **plan,
        }

    except ProviderError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error

    except Exception as error:
        _handle_telegram_error(error)


# ==========================================
# CALENDAR
# ==========================================

@router.get("/calendar/status")
async def calendar_status():
    return {
        "ics_url_configured": bool(settings.calendar_ics_url),
        "ics_file_configured": bool(settings.calendar_ics_file),
    }


@router.get("/calendar/upcoming")
async def calendar_upcoming(
    days: int = Query(default=14, ge=1, le=60),
):
    return {"events": await calendar_service.get_upcoming(days=days)}


@router.get("/calendar/study-plan")
async def calendar_study_plan(
    days: int = Query(default=7, ge=1, le=14),
    deadlines: str | None = Query(default=None, max_length=4000),
):
    try:
        return await calendar_service.build_calendar_study_plan(
            days=days,
            deadlines_text=deadlines or "",
        )

    except ProviderError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error


def _parse_local_datetime(value: str) -> str:
    from datetime import datetime, timezone

    parsed = datetime.fromisoformat(value)

    if parsed.tzinfo is None:
        parsed = parsed.astimezone()

    return parsed.astimezone(timezone.utc).isoformat()


@router.post("/calendar/events")
async def create_calendar_event(request: CalendarEventCreate):
    from backend.memory.database import create_calendar_event

    if request.start >= request.end:
        raise HTTPException(
            status_code=400,
            detail="Event start must be before its end.",
        )

    try:
        event_id = await create_calendar_event(
            request.title,
            _parse_local_datetime(request.start),
            _parse_local_datetime(request.end),
            request.notes,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format: {error}",
        ) from error

    return {"success": True, "event_id": event_id}


@router.put("/calendar/events/{event_id}")
async def update_calendar_event(
    event_id: int,
    request: CalendarEventUpdate,
):
    from backend.memory.database import (
        get_event_by_id,
        update_calendar_event,
    )

    existing = await get_event_by_id(event_id)

    if not existing:
        raise HTTPException(
            status_code=404,
            detail="Event not found.",
        )

    start_utc = (
        _parse_local_datetime(request.start)
        if request.start
        else None
    )

    end_utc = (
        _parse_local_datetime(request.end)
        if request.end
        else None
    )

    if start_utc and end_utc and start_utc >= end_utc:
        raise HTTPException(
            status_code=400,
            detail="Event start must be before its end.",
        )

    success = await update_calendar_event(
        event_id,
        title=request.title,
        start_utc=start_utc,
        end_utc=end_utc,
        notes=request.notes,
    )

    if not success:
        raise HTTPException(
            status_code=400,
            detail="No changes supplied or update failed.",
        )

    return {"success": True}


@router.delete("/calendar/events/{event_id}")
async def delete_calendar_event(event_id: int):
    from backend.memory.database import delete_calendar_event

    success = await delete_calendar_event(event_id)

    if not success:
        raise HTTPException(
            status_code=404,
            detail="Event not found.",
        )

    return {"success": True}
