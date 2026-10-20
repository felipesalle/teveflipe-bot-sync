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

    # 1. LOST DETALLE
    print("=== ANALIZANDO LOST (PERDIDOS) ENTRE 572730 Y 572860 ===")
    lost_files = {}
    async for m in client_comm.iter_messages(comm_ent, min_id=572730, max_id=572865):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if fn.lower().endswith(('.mkv', '.mp4')) and ('perdidos' in fn.lower() or 'lost' in fn.lower()):
                s, e = parse_episode_sort_key(fn)
                if s != 99:
                    lost_files[(s, e)] = (m.id, fn, m.file.size)

    print(f"Total episodios encontrados para Lost: {len(lost_files)}")
    by_s = {}
    for (s, e), val in lost_files.items():
        by_s.setdefault(s, []).append(e)

    for s in sorted(by_s.keys()):
        eps = sorted(by_s[s])
        print(f"  Temporada {s}: {len(eps)} eps -> min {eps[0]}, max {eps[-1]} (Faltan: {set(range(1, eps[-1]+1)) - set(eps)})")

    # 2. LEFTOVERS DETALLE
    print("\n=== ANALIZANDO THE LEFTOVERS ===")
    left_files = {}
    # S1E01
    m1 = await client_comm.get_messages(comm_ent, ids=181621)
    if m1 and m1.file:
        left_files[(1, 1)] = (m1.id, getattr(m1.file, 'name', ''))

    async for m in client_comm.iter_messages(comm_ent, min_id=530935, max_id=530970):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            s, e = parse_episode_sort_key(fn)
            if s != 99 and fn.lower().endswith(('.mkv', '.mp4')):
                left_files[(s, e)] = (m.id, fn)

    print(f"Total episodios The Leftovers: {len(left_files)}")
    by_s_l = {}
    for (s, e), val in left_files.items():
        by_s_l.setdefault(s, []).append(e)
    for s in sorted(by_s_l.keys()):
        eps = sorted(by_s_l[s])
        print(f"  Temporada {s}: {len(eps)} eps -> min {eps[0]}, max {eps[-1]} (Faltan: {set(range(1, eps[-1]+1)) - set(eps)})")

    # 3. FARGO DETALLE
    print("\n=== ANALIZANDO FARGO EN 458000 - 458050 ===")
    fargo_files = {}
    async for m in client_comm.iter_messages(comm_ent, min_id=458000, max_id=458050):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            s, e = parse_episode_sort_key(fn)
            if s != 99 and fn.lower().endswith(('.mkv', '.mp4')) and 'fargo' in fn.lower():
                fargo_files[(s, e)] = (m.id, fn)

    print(f"Total episodios Fargo: {len(fargo_files)}")
    by_s_f = {}
    for (s, e), val in fargo_files.items():
        by_s_f.setdefault(s, []).append(e)
    for s in sorted(by_s_f.keys()):
        eps = sorted(by_s_f[s])
        print(f"  Temporada {s}: {len(eps)} eps -> min {eps[0]}, max {eps[-1]} (Faltan: {set(range(1, eps[-1]+1)) - set(eps)})")

    await client_comm.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
