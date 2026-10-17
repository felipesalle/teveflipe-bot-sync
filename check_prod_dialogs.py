import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")

async def main():
    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client:
        me = await client.get_me()
        print(f"Logged in as {me.first_name} ({me.id})")
        async for dialog in client.iter_dialogs():
            if "castellana" in dialog.name.lower() or "1905652210" in str(dialog.id):
                print(f"FOUND: {dialog.id} | {dialog.name}")

if __name__ == "__main__":
    asyncio.run(main())
