import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")
PROD_ESTRENOS = -1003763464899

async def main():
    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client:
        channel = await client.get_entity(PROD_ESTRENOS)
        print("=== ULTIMOS 25 MENSAJES DE ESTRENOS EN PRODUCCION ===")
        async for m in client.iter_messages(channel, limit=25):
            fn = m.file.name if m.file else ""
            txt = (m.text or "")[:40]
            print(f"ID {m.id} | Archivo: {fn} | Text: {repr(txt)}")

if __name__ == "__main__":
    asyncio.run(main())
