import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
TELEGRAM_STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION", "")
PROD_SERIES = -1004331019870

async def main():
    async with TelegramClient(StringSession(TELEGRAM_STRING_SESSION), API_ID, API_HASH) as client:
        print("Cargando diálogos de TELEGRAM_STRING_SESSION...")
        dialogs = await client.get_dialogs(limit=100)
        found = False
        for d in dialogs:
            if "series tv" in d.title.lower():
                print(f"Encontrado diálogo: '{d.title}' (ID: {d.id})")
                found = True
        
        try:
            ent = await client.get_entity(PROD_SERIES)
            print(f"✅ Éxito resolviendo PROD_SERIES: '{ent.title}' ({ent.id})")
        except Exception as e:
            print(f"❌ Error resolviendo PROD_SERIES: {e}")

if __name__ == "__main__":
    asyncio.run(main())
