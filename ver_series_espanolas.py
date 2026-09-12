import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(os.getenv("TELEGRAM_API_ID") or 0)
API_HASH = os.getenv("TELEGRAM_API_HASH") or ""
STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION") or ""

async def check():
    async with TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH) as client:
        for cid in [-1004419790119, -5357361762]:
            try:
                ent = await client.get_entity(cid)
                print(f"ID: {cid} -> Titulo: {getattr(ent, 'title', 'N/A')}, forum: {getattr(ent, 'forum', False)}, megagroup: {getattr(ent, 'megagroup', False)}")
            except Exception as e:
                print(f"ID: {cid} -> Error: {e}")

if __name__ == "__main__":
    asyncio.run(check())
