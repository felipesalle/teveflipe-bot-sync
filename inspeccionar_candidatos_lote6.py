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

async def check_lost_s1(client_comm, comm_ent):
    print("\n" + "="*60)
    print("1. LOST T1 ANTES DE 572750")
    print("="*60)
    async for m in client_comm.iter_messages(comm_ent, min_id=572700, max_id=572760):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            print(f"  [{m.id}] {fn}")

async def check_stranger_things(client_comm, comm_ent):
    print("\n" + "="*60)
    print("2. STRANGER THINGS EN COMUNIDAD")
    print("="*60)
    for q in ["Stranger Things S01", "Stranger Things 1x01", "Stranger Things S04", "Stranger Things"]:
        print(f"--- Buscando: {q} ---")
        cnt = 0
        async for m in client_comm.iter_messages(comm_ent, search=q, limit=15):
            if m.file:
                fn = getattr(m.file, 'name', '') or ''
                print(f"  [{m.id}] {fn}")
                cnt += 1
            if cnt >= 5:
                break

async def check_fargo(client_comm, comm_ent):
    print("\n" + "="*60)
    print("3. FARGO EN COMUNIDAD")
    print("="*60)
    async for m in client_comm.iter_messages(comm_ent, search="Fargo", limit=30):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if 'fargo' in fn.lower():
                print(f"  [{m.id}] {fn}")

async def check_the_bear(client_comm, comm_ent):
    print("\n" + "="*60)
    print("4. THE BEAR EN COMUNIDAD")
    print("="*60)
    async for m in client_comm.iter_messages(comm_ent, search="The Bear S0", limit=30):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if 'masha' not in fn.lower():
                print(f"  [{m.id}] {fn}")

async def check_dark(client_comm, comm_ent):
    print("\n" + "="*60)
    print("5. DARK EN COMUNIDAD (T1, T2, T3)")
    print("="*60)
    for q in ["Dark S01", "Dark S02", "Dark S03", "Dark 3x01"]:
        print(f"--- Buscando {q} ---")
        async for m in client_comm.iter_messages(comm_ent, search=q, limit=10):
            if m.file:
                fn = getattr(m.file, 'name', '') or ''
                print(f"  [{m.id}] {fn}")

async def main():
    client_comm = TelegramClient(StringSession(TELEGRAM_STRING_SESSION), API_ID, API_HASH)
    client_prod = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)
    await client_comm.connect()
    await client_prod.connect()

    comm_ent = await client_comm.get_entity(COMMUNITY_SERIES)
    retro_ent = await client_prod.get_entity(RETRO_SERIES)

    await check_lost_s1(client_comm, comm_ent)
    await check_stranger_things(client_comm, comm_ent)
    await check_fargo(client_comm, comm_ent)
    await check_the_bear(client_comm, comm_ent)
    await check_dark(client_comm, comm_ent)

    await client_comm.disconnect()
    await client_prod.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
