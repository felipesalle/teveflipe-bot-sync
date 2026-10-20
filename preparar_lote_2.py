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

async def check_pb(client_comm, comm_ent):
    print("\n" + "="*60)
    print("1. PEAKY BLINDERS (36 episodios)")
    print("="*60)
    pb_files = []
    async for m in client_comm.iter_messages(comm_ent, search="Peaky Blinders", limit=160):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if fn.lower().endswith(('.mkv', '.mp4')) and 'peaky blinders' in fn.lower():
                s, e = parse_episode_sort_key(fn)
                if 1 <= s <= 6 and 1 <= e <= 6:
                    pb_files.append((s, e, m.id, fn, m.file.size))

    by_ep = {}
    for s, e, mid, fn, sz in pb_files:
        by_ep.setdefault((s, e), []).append((mid, fn, sz))

    missing = []
    selected = {}
    for s in range(1, 7):
        for e in range(1, 7):
            variants = by_ep.get((s, e), [])
            if not variants:
                missing.append((s, e))
            else:
                # Ordenar por tamaño y preferir 1080p
                best = sorted(variants, key=lambda x: (1 if '1080' in x[1] else 0, x[2]), reverse=True)[0]
                selected[(s, e)] = best

    print(f"Total cubiertos: {len(selected)} / 36 | Faltantes: {missing}")
    return selected

async def check_bm(client_comm, comm_ent):
    print("\n" + "="*60)
    print("2. BLACK MIRROR (T1-T6)")
    print("="*60)
    # T1: 3 caps, T2: 3 caps + Blanca Navidad (ep 4 o especial), T3: 6 caps, T4: 6 caps, T5: 3 caps, T6: 5 caps
    bm_files = []
    async for m in client_comm.iter_messages(comm_ent, search="Black Mirror", limit=150):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if fn.lower().endswith(('.mkv', '.mp4')) and 'black mirror' in fn.lower():
                s, e = parse_episode_sort_key(fn)
                if 1 <= s <= 6 and 1 <= e <= 10:
                    bm_files.append((s, e, m.id, fn, m.file.size))

    by_ep = {}
    for s, e, mid, fn, sz in bm_files:
        by_ep.setdefault((s, e), []).append((mid, fn, sz))

    selected = {}
    expected = {1: 3, 2: 4, 3: 6, 4: 6, 5: 3, 6: 5}
    missing = []
    for s, max_e in expected.items():
        for e in range(1, max_e + 1):
            variants = by_ep.get((s, e), [])
            if not variants:
                missing.append((s, e))
            else:
                best = sorted(variants, key=lambda x: (1 if '1080' in x[1] else 0, x[2]), reverse=True)[0]
                selected[(s, e)] = best

    print(f"Total cubiertos: {len(selected)} / {sum(expected.values())} | Faltantes: {missing}")
    return selected

async def check_chernobyl(client_comm, comm_ent):
    print("\n" + "="*60)
    print("3. CHERNOBYL (5 episodios)")
    print("="*60)
    ch_files = []
    async for m in client_comm.iter_messages(comm_ent, search="Chernobyl", limit=30):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if fn.lower().endswith(('.mkv', '.mp4')) and 'chernobyl' in fn.lower():
                s, e = parse_episode_sort_key(fn)
                if s == 1 and 1 <= e <= 5:
                    ch_files.append((s, e, m.id, fn, m.file.size))

    by_ep = {}
    for s, e, mid, fn, sz in ch_files:
        by_ep.setdefault((s, e), []).append((mid, fn, sz))

    selected = {}
    missing = []
    for e in range(1, 6):
        variants = by_ep.get((1, e), [])
        if not variants:
            missing.append((1, e))
        else:
            best = sorted(variants, key=lambda x: x[2], reverse=True)[0]
            selected[(1, e)] = best

    print(f"Total cubiertos: {len(selected)} / 5 | Faltantes: {missing}")
    return selected

async def main():
    client_comm = TelegramClient(StringSession(TELEGRAM_STRING_SESSION), API_ID, API_HASH)
    await client_comm.connect()
    comm_ent = await client_comm.get_entity(COMMUNITY_SERIES)

    pb = await check_pb(client_comm, comm_ent)
    bm = await check_bm(client_comm, comm_ent)
    ch = await check_chernobyl(client_comm, comm_ent)

    await client_comm.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
