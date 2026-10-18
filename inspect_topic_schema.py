import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetForumTopicsRequest

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")
PROD_SERIES = -1004331019870

async def main():
    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client:
        chat = await client.get_entity(PROD_SERIES)
        res = await client(GetForumTopicsRequest(peer=chat, offset_date=None, offset_id=0, offset_topic=0, limit=5))
        for t in res.topics:
            print(f"Topic {t.id} '{t.title}': {t.to_dict()}")

if __name__ == "__main__":
    asyncio.run(main())
