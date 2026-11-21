
from fastapi import APIRouter, HTTPException, Query

from backend.integrations.telegram import client as telegram_client
from backend.integrations.telegram import digest as telegram_digest
from backend.providers.manager import ProviderError


router = APIRouter(
    prefix="/api/integrations",
    tags=["Integrations"],
)


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

        return await telegram_digest.build_study_plan(
            kind=kind,
            days=days,
            deadlines_text=deadlines_text,
        )

    except ProviderError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error

    except Exception as error:
        _handle_telegram_error(error)
