
"""
Interactive helper that generates a Telegram session string for Jarvis.

This script ONLY logs your account in and saves the session string
directly into the project .env file. It never reads or sends any
group messages, and the session string is never displayed on screen.

Steps:
1. Create an app at https://my.telegram.org to get api_id and api_hash.
2. Add TELEGRAM_API_ID and TELEGRAM_API_HASH to .env (optional; the
   script will ask for them if missing).
3. Run this script from the project root with the venv activated:
       python scripts/telegram_login.py
"""

import asyncio
import os

from getpass import getpass

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ENV_PATH = os.path.join(PROJECT_ROOT, ".env")

load_dotenv(ENV_PATH)


def save_session_to_env(session_string):
    """Write TELEGRAM_SESSION into .env without printing it anywhere."""

    lines = []

    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()

    replaced = False
    updated = []

    for line in lines:
        if line.strip().startswith("TELEGRAM_SESSION="):
            updated.append(f"TELEGRAM_SESSION={session_string}")
            replaced = True
        else:
            updated.append(line)

    if not replaced:
        updated.append(f"TELEGRAM_SESSION={session_string}")

    with open(ENV_PATH, "w", encoding="utf-8") as handle:
        handle.write("\n".join(updated) + "\n")


async def main():
    api_id = os.getenv("TELEGRAM_API_ID") or input("api_id: ").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH") or input("api_hash: ").strip()

    if not api_id or not api_hash:
        print("api_id and api_hash are required.")
        return

    async with TelegramClient(
        StringSession(),
        int(api_id),
        api_hash,
    ) as client:
        if not await client.is_user_authorized():
            phone = input("Phone number (with country code): ").strip()

            await client.send_code_request(phone)

            code = input("Login code Telegram sent you: ").strip()

            await client.sign_in(phone, code)

            password = getpass(
                "Two-factor password (leave empty if none): "
            )

            if password:
                await client.sign_in(password=password)

        session_string = client.session.save()

    save_session_to_env(session_string)

    print()
    print(
        f"TELEGRAM_SESSION saved to .env "
        f"({len(session_string)} characters, not displayed)."
    )
    print("Keep .env private: the session grants read access to your account.")
    print("Jarvis never sends messages; it only reads configured groups.")


if __name__ == "__main__":
    asyncio.run(main())
