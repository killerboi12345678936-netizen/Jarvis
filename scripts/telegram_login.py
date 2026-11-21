
"""
Interactive helper that generates a Telegram session string for Jarvis.

This script ONLY logs your account in and prints a session string.
It never reads or sends any group messages.

Steps:
1. Create an app at https://my.telegram.org to get api_id and api_hash.
2. Run this script from the project root with the venv activated:
       python scripts/telegram_login.py
3. Paste the printed session string into .env as TELEGRAM_SESSION=...
"""

import asyncio
import os

from getpass import getpass

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))


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

    print()
    print("Add this line to your .env file:")
    print()
    print(f"TELEGRAM_SESSION={session_string}")
    print()
    print("Keep it private: it grants full read access to your account.")
    print("Jarvis never sends messages; it only reads configured groups.")


if __name__ == "__main__":
    asyncio.run(main())
