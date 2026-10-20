import asyncio
import os
import re
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
TELEGRAM_STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION", "")
COMMUNITY_SERIES = -1002257262928

async def main():
    client_comm = TelegramClient(StringSession(TELEGRAM_STRING_SESSION), API_ID, API_HASH)
    await client_comm.connect()
    comm_ent = await client_comm.get_entity(COMMUNITY_SERIES)

    # 1. Ver qué hay antes del mensaje 262235 (posible Temporada 1 de The Americans)
    print("=== INSPECCIONANDO MENSAJES 262200 - 262235 ===")
    async for m in client_comm.iter_messages(comm_ent, min_id=262200, max_id=262236):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            print(f"[{m.id}] {fn}")

    # 2. Ver Chernobyl
    print("\n=== BUSCANDO CHERNOBYL ===")
    async for m in client_comm.iter_messages(comm_ent, search="Chernobyl", limit=15):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            print(f"[{m.id}] {fn}")

    # 3. Ver Fleabag
    print("\n=== BUSCANDO FLEABAG ===")
    async for m in client_comm.iter_messages(comm_ent, search="Fleabag", limit=20):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            print(f"[{m.id}] {fn}")

    await client_comm.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
