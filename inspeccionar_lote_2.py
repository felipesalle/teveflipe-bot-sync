import asyncio
import os
import re
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")
TELEGRAM_STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION", "")

COMMUNITY_SERIES = -1002257262928
RETRO_SERIES = -1003865750796
BUNKER_SERIES = -1002097175258

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

async def check_series(client_comm, client_prod, query, title):
    print(f"\n{'='*70}\n🔍 INSPECCIONANDO: {title} (búsqueda: '{query}')\n{'='*70}")
    comm_ent = await client_comm.get_entity(COMMUNITY_SERIES)
    retro_ent = await client_prod.get_entity(RETRO_SERIES)
    
    results = []
    # Buscar en Comunidad
    async for m in client_comm.iter_messages(comm_ent, search=query, limit=150):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if fn.lower().endswith(('.mkv', '.mp4')):
                results.append(('Comunidad', m.id, fn, parse_episode_sort_key(fn), m.date))

    # Buscar en Retro
    async for m in client_prod.iter_messages(retro_ent, search=query, limit=150):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if fn.lower().endswith(('.mkv', '.mp4')):
                results.append(('Retro', m.id, fn, parse_episode_sort_key(fn), m.date))

    # Filtrar que el título sea relevante
    filtered = [r for r in results if any(w in r[2].lower() for w in query.lower().split())]
    filtered.sort(key=lambda x: (x[3][0], x[3][1], x[1]))

    print(f"Total archivos encontrados: {len(filtered)}")
    # Agrupar por temporada
    seasons = {}
    for src, mid, fn, key, dt in filtered:
        s, e = key
        seasons.setdefault(s, []).append((e, fn, src, mid))

    for s in sorted(seasons.keys()):
        eps = seasons[s]
        unique_eps = sorted(set(x[0] for x in eps))
        print(f"  Temporada {s}: {len(eps)} archivos encontrados ({len(unique_eps)} episodios únicos: {unique_eps})")
        for e, fn, src, mid in eps[:3]:
            print(f"    - S{s:02d}E{e:02d} [{src} msg {mid}]: {fn}")
        if len(eps) > 3:
            print(f"    ... (+{len(eps)-3} más)")

async def main():
    client_prod = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)
    client_comm = TelegramClient(StringSession(TELEGRAM_STRING_SESSION), API_ID, API_HASH)
    await client_prod.connect()
    await client_comm.connect()

    await check_series(client_comm, client_prod, "Peaky Blinders", "PEAKY BLINDERS")
    await check_series(client_comm, client_prod, "The Americans", "THE AMERICANS")
    await check_series(client_comm, client_prod, "Black Mirror", "BLACK MIRROR")

    await client_prod.disconnect()
    await client_comm.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
