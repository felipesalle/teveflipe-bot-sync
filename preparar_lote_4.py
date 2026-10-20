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

    print("=== INSPECCIÓN MENSAJES 282092 - 282104 (HERMANOS DE SANGRE) ===")
    async for m in client_comm.iter_messages(comm_ent, min_id=282092, max_id=282104):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            print(f"[{m.id}] {fn} ({m.file.size/(1024*1024):.1f} MB)")

    print("\n=== INSPECCIÓN MENSAJES 458063 - 458072 (TRUE DETECTIVE T1) ===")
    async for m in client_comm.iter_messages(comm_ent, min_id=458063, max_id=458073):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            print(f"[{m.id}] {fn} ({m.file.size/(1024*1024):.1f} MB)")

    await client_comm.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
