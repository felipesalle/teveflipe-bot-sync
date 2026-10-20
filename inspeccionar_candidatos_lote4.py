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

async def check_series_in_channel(client, entity, query, name):
    print(f"\n{'='*60}\n🔍 Buscando {name} ('{query}')...\n{'='*60}")
    found = []
    async for m in client.iter_messages(entity, search=query, limit=160):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            ext = os.path.splitext(fn)[1].lower()
            key = parse_episode_sort_key(fn)
            found.append((m.id, fn, ext, key, m.file.size))

    # Filtrar que el título tenga sentido
    video_files = [f for f in found if f[2] in ('.mkv', '.mp4')]
    non_video = [f for f in found if f[2] not in ('.mkv', '.mp4')]
    if non_video:
        print(f"⚠️ Archivos NO video encontrados: {len(non_video)}")

    by_season = {}
    for mid, fn, ext, key, sz in video_files:
        s, e = key
        by_season.setdefault(s, {}).setdefault(e, []).append((mid, fn, ext, sz))

    for s in sorted(by_season.keys()):
        eps = by_season[s]
        print(f"  Temporada {s}: {len(eps)} episodios cubiertos -> {sorted(eps.keys())}")
        for e in sorted(eps.keys())[:2]:
            b = eps[e][0]
            print(f"    S{s:02d}E{e:02d} [msg {b[0]}]: {b[1]} ({b[3]/(1024*1024):.1f} MB)")
        if len(eps) > 2:
            last_e = sorted(eps.keys())[-1]
            b_last = eps[last_e][0]
            print(f"    ... hasta S{s:02d}E{last_e:02d} [msg {b_last[0]}]: {b_last[1]}")

async def main():
    client_comm = TelegramClient(StringSession(TELEGRAM_STRING_SESSION), API_ID, API_HASH)
    client_prod = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)
    await client_comm.connect()
    await client_prod.connect()

    comm_ent = await client_comm.get_entity(COMMUNITY_SERIES)
    retro_ent = await client_prod.get_entity(RETRO_SERIES)

    await check_series_in_channel(client_comm, comm_ent, "True Detective", "TRUE DETECTIVE")
    await check_series_in_channel(client_comm, comm_ent, "The Bear", "THE BEAR")
    await check_series_in_channel(client_comm, comm_ent, "BoJack Horseman", "BOJACK HORSEMAN")
    await check_series_in_channel(client_comm, comm_ent, "Stranger Things", "STRANGER THINGS")
    await check_series_in_channel(client_comm, comm_ent, "The Leftovers", "THE LEFTOVERS")
    await check_series_in_channel(client_comm, comm_ent, "Hermanos de Sangre", "HERMANOS DE SANGRE (BAND OF BROTHERS)")

    await client_comm.disconnect()
    await client_prod.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
