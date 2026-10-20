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

async def main():
    client_comm = TelegramClient(StringSession(TELEGRAM_STRING_SESSION), API_ID, API_HASH)
    await client_comm.connect()
    comm_ent = await client_comm.get_entity(COMMUNITY_SERIES)

    print("=== INSPECCIÓN THE LEFTOVERS ===")
    async for m in client_comm.iter_messages(comm_ent, search="The Leftovers", limit=50):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if fn.lower().endswith(('.mkv', '.mp4')):
                print(f"[{m.id}] {fn}")

    print("\n=== INSPECCIÓN STRANGER THINGS ===")
    st = {}
    async for m in client_comm.iter_messages(comm_ent, search="Stranger Things", limit=80):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if fn.lower().endswith(('.mkv', '.mp4')) and 'stranger' in fn.lower():
                print(f"[{m.id}] {fn}")

    await client_comm.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
