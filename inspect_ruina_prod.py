import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")
PROD_80_90 = -1004467288762

async def main():
    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client:
        channel = await client.get_entity(PROD_80_90)
        print("Buscando en Producción 80 y 90:", channel.title)
        count = 0
        async for msg in client.iter_messages(channel, search="ruina"):
            fname = msg.file.name if msg.file else ""
            print(f"ID: {msg.id} | Archivo: {fname} | Texto: {repr(msg.text)}")
            count += 1
        async for msg in client.iter_messages(channel, search="money pit"):
            fname = msg.file.name if msg.file else ""
            print(f"ID (money pit): {msg.id} | Archivo: {fname} | Texto: {repr(msg.text)}")
            count += 1
        print(f"Total encontrados: {count}")

if __name__ == "__main__":
    asyncio.run(main())
