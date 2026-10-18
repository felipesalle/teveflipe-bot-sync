import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetForumTopicsRequest

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")
PROD_SERIES = -1004331019870

TARGET_SERIES = [
    "Younger",
    "Your Honor",
    "Honor",
    "Young Pope",
    "Your Pretty Face",
    "Watching You",
    "All You Need Is Crime",
    "You"
]

async def main():
    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client:
        prod_entity = await client.get_entity(PROD_SERIES)
        print("Buscando si ya existen temas dedicados para estas series en Series TV...")

        offset_date = None
        offset_id = 0
        offset_topic = 0
        found_topics = []

        while True:
            res = await client(GetForumTopicsRequest(
                peer=prod_entity,
                offset_date=offset_date,
                offset_id=offset_id,
                offset_topic=offset_topic,
                limit=100
            ))
            if not res.topics:
                break

            for t in res.topics:
                t_title = t.title
                for target in TARGET_SERIES:
                    if target.lower() in t_title.lower():
                        found_topics.append((t.id, t_title))

            if len(res.topics) < 100:
                break

            offset_topic = res.topics[-1].id
            offset_id = res.messages[-1].id if res.messages else 0
            offset_date = res.messages[-1].date if res.messages else None

        print("\n=== TEMAS ENCONTRADOS COINCIDENTES EN PRODUCCIÓN ===")
        for tid, title in found_topics:
            print(f"- Topic {tid}: {title}")

if __name__ == "__main__":
    asyncio.run(main())
