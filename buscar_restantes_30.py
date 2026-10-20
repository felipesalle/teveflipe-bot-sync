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

async def check(client_comm, client_prod, comm_ent, retro_ent, name, queries):
    print(f"\n{'='*60}\n🔍 BUSCANDO: {name} (consultas: {queries})\n{'='*60}")
    files = []
    for q in queries:
        # Buscar en Comunidad
        async for m in client_comm.iter_messages(comm_ent, search=q, limit=100):
            if m.file:
                fn = getattr(m.file, 'name', '') or ''
                if fn.lower().endswith(('.mkv', '.mp4')):
                    files.append(('Comunidad', m.id, fn, parse_episode_sort_key(fn), m.file.size))
        # Buscar en Retro
        async for m in client_prod.iter_messages(retro_ent, search=q, limit=100):
            if m.file:
                fn = getattr(m.file, 'name', '') or ''
                if fn.lower().endswith(('.mkv', '.mp4')):
                    files.append(('Retro', m.id, fn, parse_episode_sort_key(fn), m.file.size))

    # Deduplicar por msg.id
    unique_files = {}
    for src, mid, fn, key, sz in files:
        unique_files[mid] = (src, mid, fn, key, sz)

    by_season = {}
    for src, mid, fn, key, sz in unique_files.values():
        s, e = key
        by_season.setdefault(s, {}).setdefault(e, []).append((src, mid, fn, sz))

    for s in sorted(by_season.keys()):
        eps = by_season[s]
        print(f"  Temporada {s}: {len(eps)} episodios cubiertos -> {sorted(eps.keys())}")
        first_e = sorted(eps.keys())[0]
        f = eps[first_e][0]
        print(f"    S{s:02d}E{first_e:02d} [{f[0]} msg {f[1]}]: {f[2]} ({f[3]/(1024*1024):.1f} MB)")
        if len(eps) > 1:
            last_e = sorted(eps.keys())[-1]
            l = eps[last_e][0]
            print(f"    ... hasta S{s:02d}E{last_e:02d} [{l[0]} msg {l[1]}]: {l[2]}")

async def main():
    client_comm = TelegramClient(StringSession(TELEGRAM_STRING_SESSION), API_ID, API_HASH)
    client_prod = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)
    await client_comm.connect()
    await client_prod.connect()

    comm_ent = await client_comm.get_entity(COMMUNITY_SERIES)
    retro_ent = await client_prod.get_entity(RETRO_SERIES)

    await check(client_comm, client_prod, comm_ent, retro_ent, "THE WIRE / BAJO ESCUCHA", ["The Wire", "Bajo escucha"])
    await check(client_comm, client_prod, comm_ent, retro_ent, "LOST / PERDIDOS", ["Lost", "Perdidos"])
    await check(client_comm, client_prod, comm_ent, retro_ent, "THE LEFTOVERS", ["The Leftovers", "Leftovers"])
    await check(client_comm, client_prod, comm_ent, retro_ent, "STRANGER THINGS", ["Stranger Things"])
    await check(client_comm, client_prod, comm_ent, retro_ent, "SEVERANCE / SEPARACION", ["Severance", "Separación"])
    await check(client_comm, client_prod, comm_ent, retro_ent, "DARK", ["Dark S01", "Dark S02", "Dark S03", "Dark 1x", "Dark 2x", "Dark 3x"])
    await check(client_comm, client_prod, comm_ent, retro_ent, "THE BEAR", ["The Bear S01", "The Bear S02", "The Bear S03", "The Bear 1x", "The Bear 2x", "The Bear 3x"])
    await check(client_comm, client_prod, comm_ent, retro_ent, "FARGO", ["Fargo S01", "Fargo S02", "Fargo S03", "Fargo 1x", "Fargo 2x"])

    await client_comm.disconnect()
    await client_prod.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
