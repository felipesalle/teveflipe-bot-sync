import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetForumTopicsRequest

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_BUNKER = os.getenv("SESSION_BUNKER", "")
BUNKER_SERIES = -1002097175258

async def main():
    async with TelegramClient(StringSession(SESSION_BUNKER), API_ID, API_HASH) as client:
        bunker_entity = await client.get_entity(BUNKER_SERIES)
        print(f"Buscando topics en Búnker ({bunker_entity.title})...")

        offset_date = None
        offset_id = 0
        offset_topic = 0
        found = []

        while True:
            res = await client(GetForumTopicsRequest(
                peer=bunker_entity,
                offset_date=offset_date,
                offset_id=offset_id,
                offset_topic=offset_topic,
                limit=100
            ))
            if not res.topics:
                break

            for t in res.topics:
                title_lower = t.title.lower()
                for target in ["you", "younger", "honor", "young pope", "pretty face", "watching you", "crime"]:
                    if target in title_lower:
                        found.append((t.id, t.title))

            if len(res.topics) < 100:
                break

            offset_topic = res.topics[-1].id
            offset_id = res.messages[-1].id if res.messages else 0
            offset_date = res.messages[-1].date if res.messages else None

        print("\n=== TEMAS ENCONTRADOS EN BÚNKER ===")
        for tid, title in found:
            print(f"- Topic {tid}: {title}")

if __name__ == "__main__":
    asyncio.run(main())
