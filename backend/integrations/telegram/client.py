
import logging

from datetime import datetime, timedelta, timezone

from telethon import TelegramClient
from telethon.sessions import StringSession

from backend.core.config import settings


logger = logging.getLogger(__name__)


class TelegramNotConfigured(RuntimeError):
    pass


_client = None


def get_client():
    global _client

    if not settings.telegram_api_id or not settings.telegram_api_hash:
        raise TelegramNotConfigured(
            "TELEGRAM_API_ID and TELEGRAM_API_HASH are not set. "
            "Create an app at my.telegram.org and add them to .env."
        )

    if not settings.telegram_session:
        raise TelegramNotConfigured(
            "TELEGRAM_SESSION is not set. Run "
            "scripts/telegram_login.py to generate a session string."
        )

    if _client is None:
        _client = TelegramClient(
            StringSession(settings.telegram_session),
            settings.telegram_api_id,
            settings.telegram_api_hash,
        )

    return _client


async def ensure_connected():
    client = get_client()

    if not client.is_connected():
        await client.connect()

    if not await client.is_user_authorized():
        raise TelegramNotConfigured(
            "The Telegram session is not authorized. Regenerate it "
            "with scripts/telegram_login.py."
        )

    return client


def configured_groups():
    return {
        subject: group
        for subject, group in settings.telegram_groups.items()
        if group
    }


def status():
    return {
        "credentials_present": bool(
            settings.telegram_api_id
            and settings.telegram_api_hash
            and settings.telegram_session
        ),
        "groups": settings.telegram_groups,
        "active_groups": configured_groups(),
    }


async def fetch_recent_messages(hours=24, limit_per_group=200):
    """Read recent messages from the configured study groups.

    Strictly read-only: this function never sends anything.
    """

    client = await ensure_connected()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    results = {}

    for subject, group in settings.telegram_groups.items():
        if not group:
            results[subject] = {
                "configured": False,
                "messages": [],
            }

            continue

        try:
            entity = await client.get_entity(group)

            messages = []

            async for message in client.iter_messages(
                entity,
                limit=limit_per_group,
            ):
                if message.date and message.date < cutoff:
                    break

                if message.action:
                    continue

                sender_name = ""

                if message.sender:
                    sender_name = getattr(
                        message.sender,
                        "first_name",
                        "",
                    ) or getattr(message.sender, "title", "") or ""

                messages.append({
                    "sender": sender_name,
                    "text": (message.message or "").strip(),
                    "date": message.date.astimezone().isoformat(),
                    "has_media": bool(message.media),
                })

            messages.reverse()

            results[subject] = {
                "configured": True,
                "title": getattr(entity, "title", group),
                "messages": messages,
            }

        except Exception as error:
            logger.warning(
                "Could not read Telegram group %s: %s", group, error,
            )

            results[subject] = {
                "configured": True,
                "error": str(error),
                "messages": [],
            }

    return results
