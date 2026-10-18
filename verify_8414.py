import asyncio
import os
from collections import defaultdict
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")

PROD_SERIES = -1004331019870
SOURCE_TOPIC_ID = 8414

async def main():
    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client:
        prod_entity = await client.get_entity(PROD_SERIES)

        remaining = []
        async for m in client.iter_messages(prod_entity, reply_to=SOURCE_TOPIC_ID):
            fn = m.file.name if m.file else (m.text[:35] if m.text else "Sin nombre")
            remaining.append((m.id, fn))

        print(f"Total mensajes restantes en Topic 8414: {len(remaining)}")
        print("\nMuestra de mensajes en 8414 (primeros 20):")
        for mid, fn in remaining[:20]:
            print(f"- ID {mid}: {fn}")

        # Comprobar si queda algo que no sea You
        non_you = [m for m in remaining if "you" not in m[1].lower() and m[1] != "Sin nombre"]
        print(f"\nArchivos que no contienen 'you' en el nombre: {len(non_you)}")
        for mid, fn in non_you[:20]:
            print(f"  * ID {mid}: {fn}")

if __name__ == "__main__":
    asyncio.run(main())
