import asyncio
import os
import re
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
TELEGRAM_STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION", "")
SESSION_PROD = os.getenv("SESSION_PROD", "")
COMMUNITY_SERIES = -1002257262928
RETRO_SERIES = -1003865750796

async def main():
    client_comm = TelegramClient(StringSession(TELEGRAM_STRING_SESSION), API_ID, API_HASH)
    client_prod = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)
    await client_comm.connect()
    await client_prod.connect()

    comm_ent = await client_comm.get_entity(COMMUNITY_SERIES)
    retro_ent = await client_prod.get_entity(RETRO_SERIES)

    print("=== BUSCANDO LOST / PERDIDOS EN RETRO ===")
    async for m in client_prod.iter_messages(retro_ent, search="Perdidos", limit=30):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            print(f"[{m.id}] {fn}")

    print("\n=== BUSCANDO THE BEAR EN COMUNIDAD (EXCLUYENDO MASHA) ===")
    async for m in client_comm.iter_messages(comm_ent, search="The Bear", limit=60):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if 'masha' not in fn.lower():
                print(f"[{m.id}] {fn}")

    await client_comm.disconnect()
    await client_prod.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
