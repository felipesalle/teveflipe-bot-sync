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

    print("=== EXPLORANDO FARGO EN COMUNIDAD (457900 - 458100) ===")
    fargo_msgs = []
    async for m in client_comm.iter_messages(comm_ent, min_id=457900, max_id=458100):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if 'fargo' in fn.lower():
                fargo_msgs.append((m.id, fn))
    print(f"Total en rango 457900-458100: {len(fargo_msgs)}")
    for mid, fn in fargo_msgs[:20]:
        print(f"  [{mid}] {fn}")
    for mid, fn in fargo_msgs[-10:]:
        print(f"  [{mid}] {fn}")

    print("\n=== BUSCANDO OTRAS TEMPORADAS DE FARGO (1x01, 2x01, 3x01, 5x01) ===")
    for q in ["Fargo 1x01", "Fargo 2x01", "Fargo 3x01", "Fargo 5x01"]:
        print(f"Búsqueda: {q}")
        async for m in client_comm.iter_messages(comm_ent, search=q, limit=5):
            if m.file:
                print(f"  [{m.id}] {getattr(m.file, 'name', '')}")

    await client_comm.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
