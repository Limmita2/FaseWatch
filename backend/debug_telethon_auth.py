import asyncio
import os
import sys

from telethon import TelegramClient
from telethon.errors import (
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)
from telethon.sessions import StringSession


def prompt(label: str) -> str:
    print(label, end="", flush=True)
    return sys.stdin.readline().strip()


async def main() -> None:
    phone = os.environ.get("DEBUG_TG_PHONE") or prompt("Phone: ")
    api_id = os.environ.get("DEBUG_TG_API_ID") or prompt("API ID: ")
    api_hash = os.environ.get("DEBUG_TG_API_HASH") or prompt("API Hash: ")

    client = TelegramClient(StringSession(), int(api_id), api_hash)
    await client.connect()

    try:
        print(f"Sending code to {phone}...", flush=True)
        sent = await client.send_code_request(phone)
        print(f"phone_code_hash={sent.phone_code_hash}", flush=True)

        code = prompt("Code: ")
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=sent.phone_code_hash)
        except SessionPasswordNeededError:
            password = prompt("2FA password: ")
            await client.sign_in(password=password)
        except PhoneCodeInvalidError:
            print("RESULT: PhoneCodeInvalidError", flush=True)
            return
        except PhoneCodeExpiredError:
            print("RESULT: PhoneCodeExpiredError", flush=True)
            return

        print("RESULT: authenticated", flush=True)
        print(f"session_string={client.session.save()}", flush=True)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
