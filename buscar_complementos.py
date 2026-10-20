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

    print("=== BUSCANDO THE LEFTOVERS 2x10 y 3x08 EN MKV ===")
    for q in ["Leftovers 2x10", "Leftovers S02E10", "Leftovers 3x08", "Leftovers S03E08"]:
        print(f"--- Q: {q} ---")
        async for m in client_comm.iter_messages(comm_ent, search=q, limit=5):
            if m.file:
                print(f"  [{m.id}] {getattr(m.file, 'name', '')}")

    print("\n=== BUSCANDO THE BEAR PACK LIMPIO ===")
    async for m in client_comm.iter_messages(comm_ent, search="The Bear 1080p", limit=20):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if 'masha' not in fn.lower():
                print(f"  [{m.id}] {fn}")

    print("\n=== BUSCANDO STRANGER THINGS 720p / 1080p ===")
    async for m in client_comm.iter_messages(comm_ent, search="Stranger Things 1080p", limit=20):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            print(f"  [{m.id}] {fn}")

    await client_comm.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
