import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")
BUNKER_SERIES = -1002097175258

async def main():
    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client:
        entity = await client.get_entity(BUNKER_SERIES)
        participants = await client.get_participants(entity, limit=300)
        print(f"Total miembros restantes en SERIES TV: {len(participants)}")
        for i, p in enumerate(participants[:15], 1):
            name = f"{p.first_name or ''} {p.last_name or ''}".strip()
            print(f"  {i}. {name} (ID: {p.id})")

if __name__ == "__main__":
    asyncio.run(main())
