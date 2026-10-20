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

async def inspect(client, entity, query, name, source_name):
    print(f"\n{'='*60}\n🔍 Buscando {name} en {source_name} ('{query}')...\n{'='*60}")
    found = []
    async for m in client.iter_messages(entity, search=query, limit=120):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            ext = os.path.splitext(fn)[1].lower()
            key = parse_episode_sort_key(fn)
            found.append((m.id, fn, ext, key, m.file.size))
    
    # Filtrar solo mkv y mp4
    video_files = [f for f in found if f[2] in ('.mkv', '.mp4')]
    non_video = [f for f in found if f[2] not in ('.mkv', '.mp4')]
    if non_video:
        print(f"⚠️ Atención: Encontrados {len(non_video)} archivos NO video (ej: {non_video[0][1]})")

    # Agrupar por key
    by_ep = {}
    for mid, fn, ext, key, sz in video_files:
        if key != (99, 99):
            by_ep.setdefault(key, []).append((mid, fn, ext, sz))

    print(f"Total video files: {len(video_files)} | Episodios únicos identificados: {len(by_ep)}")
    for k in sorted(by_ep.keys()):
        best = by_ep[k][0]
        print(f"  S{k[0]:02d}E{k[1]:02d} [msg {best[0]}]: {best[1]} ({best[3]/(1024*1024):.1f} MB)")
    return by_ep

async def main():
    client_comm = TelegramClient(StringSession(TELEGRAM_STRING_SESSION), API_ID, API_HASH)
    client_prod = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)
    await client_comm.connect()
    await client_prod.connect()

    comm_ent = await client_comm.get_entity(COMMUNITY_SERIES)
    retro_ent = await client_prod.get_entity(RETRO_SERIES)

    await inspect(client_comm, comm_ent, "Fleabag", "FLEABAG", "Comunidad")
    await inspect(client_comm, comm_ent, "Gambito de Dama", "GAMBITO DE DAMA", "Comunidad")
    await inspect(client_comm, comm_ent, "Arcane", "ARCANE", "Comunidad")
    await inspect(client_prod, retro_ent, "Band of Brothers", "BAND OF BROTHERS", "Retro")
    await inspect(client_comm, comm_ent, "Andor", "ANDOR", "Comunidad")

    await client_comm.disconnect()
    await client_prod.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
