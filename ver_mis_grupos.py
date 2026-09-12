import asyncio
import os
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger()

API_ID = int(os.getenv("TELEGRAM_API_ID") or 0)
API_HASH = os.getenv("TELEGRAM_API_HASH") or ""
STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION") or ""

async def check():
    async with TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH) as client:
        me = await client.get_me()
        print(f"Sesion iniciada como: {me.first_name} (ID: {me.id}, Username: @{me.username})")
        print("\n--- GRUPOS Y CANALES DEL USUARIO ---")
        async for d in client.iter_dialogs(limit=50):
            if d.is_channel or d.is_group:
                print(f"ID: {d.id} | Titulo: {d.title}")

if __name__ == "__main__":
    asyncio.run(check())
