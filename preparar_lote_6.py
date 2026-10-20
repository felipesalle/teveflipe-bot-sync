import asyncio
import os
import re
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
TELEGRAM_STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION", "")
COMMUNITY_SERIES = -1002257262928

def parse_episode_sort_key(filename: str):
    m = re.search(r'(?:(\d{1,2})\s*x\s*(\d{1,2})|[sS](\d{1,2})[._\s]*[eE](\d{1,2}))', filename)
    if m:
        season = int(m.group(1) or m.group(3))
        episode = int(m.group(2) or m.group(4))
        return (season, episode)
    m2 = re.search(r'\b(\d{1,2})(\d{2})\b', filename)
    if m2:
        return (int(m2.group(1)), int(m2.group(2)))
    return (99, 99)

async def main():
    client_comm = TelegramClient(StringSession(TELEGRAM_STRING_SESSION), API_ID, API_HASH)
    await client_comm.connect()
    comm_ent = await client_comm.get_entity(COMMUNITY_SERIES)

    # 1. LOST (119 episodios)
    lost_dict = {}
    async for m in client_comm.iter_messages(comm_ent, min_id=572730, max_id=572865):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if fn.lower().endswith(('.mkv', '.mp4')) and ('perdidos' in fn.lower() or 'lost' in fn.lower()):
                s, e = parse_episode_sort_key(fn)
                if s != 99:
                    lost_dict[(s, e)] = (m.id, fn)

    lost_sorted = sorted(lost_dict.keys())
    print(f"LOST: {len(lost_sorted)} episodios encontrados.")
    print(f"  Primer episodio: {lost_sorted[0]} -> {lost_dict[lost_sorted[0]]}")
    print(f"  Último episodio: {lost_sorted[-1]} -> {lost_dict[lost_sorted[-1]]}")

    # 2. FARGO (41 episodios)
    fargo_dict = {}
    async for m in client_comm.iter_messages(comm_ent, min_id=458000, max_id=458050):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if fn.lower().endswith(('.mkv', '.mp4')) and 'fargo' in fn.lower():
                s, e = parse_episode_sort_key(fn)
                if s != 99:
                    fargo_dict[(s, e)] = (m.id, fn)

    fargo_sorted = sorted(fargo_dict.keys())
    print(f"\nFARGO: {len(fargo_sorted)} episodios encontrados.")
    print(f"  Primer episodio: {fargo_sorted[0]} -> {fargo_dict[fargo_sorted[0]]}")
    print(f"  Último episodio: {fargo_sorted[-1]} -> {fargo_dict[fargo_sorted[-1]]}")

    await client_comm.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
