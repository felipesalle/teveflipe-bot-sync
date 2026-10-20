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

async def check_lost(client_comm, comm_ent):
    print("\n" + "="*60)
    print("1. PERDIDOS (LOST) EN COMUNIDAD (572750 - 572860)")
    print("="*60)
    lost_files = []
    async for m in client_comm.iter_messages(comm_ent, min_id=572750, max_id=572865):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if fn.lower().endswith(('.mkv', '.mp4')) and ('perdidos' in fn.lower() or 'lost' in fn.lower()):
                s, e = parse_episode_sort_key(fn)
                lost_files.append((s, e, m.id, fn, m.file.size))

    by_season = {}
    for s, e, mid, fn, sz in lost_files:
        by_season.setdefault(s, {})[e] = (mid, fn, sz)

    for s in sorted(by_season.keys()):
        eps = by_season[s]
        print(f"  Temporada {s}: {len(eps)} episodios -> {sorted(eps.keys())}")

async def check_leftovers_other(client_comm, client_prod, comm_ent, retro_ent):
    print("\n" + "="*60)
    print("2. THE LEFTOVERS EN RETRO Y OTRAS BÚSQUEDAS")
    print("="*60)
    # En Retro
    async for m in client_prod.iter_messages(retro_ent, search="Leftovers", limit=20):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            print(f"  [Retro {m.id}] {fn}")
    # En Comunidad buscando 1x01 mkv
    async for m in client_comm.iter_messages(comm_ent, search="Leftovers 1x01", limit=10):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            print(f"  [Comunidad {m.id}] {fn}")

async def check_stranger_things_clean(client_comm, client_prod, comm_ent, retro_ent):
    print("\n" + "="*60)
    print("3. STRANGER THINGS PACK COMPLETO")
    print("="*60)
    async for m in client_prod.iter_messages(retro_ent, search="Stranger Things", limit=20):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            print(f"  [Retro {m.id}] {fn}")

async def check_americans_s1(client_comm, client_prod, comm_ent, retro_ent):
    print("\n" + "="*60)
    print("4. THE AMERICANS S01E01 Y S01E09 (MKV)")
    print("="*60)
    for q in ["The Americans 1x01", "The Americans S01E01", "The Americans 1x09"]:
        async for m in client_comm.iter_messages(comm_ent, search=q, limit=5):
            if m.file:
                fn = getattr(m.file, 'name', '') or ''
                print(f"  [Comunidad {m.id}] {fn}")

async def main():
    client_comm = TelegramClient(StringSession(TELEGRAM_STRING_SESSION), API_ID, API_HASH)
    client_prod = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)
    await client_comm.connect()
    await client_prod.connect()

    comm_ent = await client_comm.get_entity(COMMUNITY_SERIES)
    retro_ent = await client_prod.get_entity(RETRO_SERIES)

    await check_lost(client_comm, comm_ent)
    await check_leftovers_other(client_comm, client_prod, comm_ent, retro_ent)
    await check_stranger_things_clean(client_comm, client_prod, comm_ent, retro_ent)
    await check_americans_s1(client_comm, client_prod, comm_ent, retro_ent)

    await client_comm.disconnect()
    await client_prod.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
