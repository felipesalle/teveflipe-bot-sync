import asyncio
import os
import re
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")
RETRO_SERIES = -1003865750796

async def main():
    client_prod = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)
    await client_prod.connect()
    retro_ent = await client_prod.get_entity(RETRO_SERIES)

    print("=== BUSCANDO EN CANAL RETRO ===")
    for q in ["Dark", "Stranger Things", "The Leftovers", "Leftovers", "The Bear", "The Americans"]:
        print(f"\n--- Búsqueda en Retro: '{q}' ---")
        cnt = 0
        async for m in client_prod.iter_messages(retro_ent, search=q, limit=10):
            if m.file:
                cnt += 1
                print(f"  [{m.id}] {getattr(m.file, 'name', '')}")
        if cnt == 0:
            print("  (No se encontraron archivos)")

    await client_prod.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
