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
TOPIC_BB = 27949

def parse_episode_sort_key(filename: str):
    m = re.search(r'(?:(\d{1,2})\s*x\s*(\d{1,2})|[sS](\d{1,2})[._\s]*[eE](\d{1,2}))', filename)
    if m:
        season = int(m.group(1) or m.group(3))
        episode = int(m.group(2) or m.group(4))
        return (season, episode)
    return (99, 99)

async def main():
    client_prod = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)
    client_comm = TelegramClient(StringSession(TELEGRAM_STRING_SESSION), API_ID, API_HASH)
    await client_prod.connect()
    await client_comm.connect()

    # 1. Ver qué hay actualmente en el Topic 27949 de Breaking Bad en Búnker
    bunker_ent = await client_prod.get_entity(BUNKER_SERIES)
    current_bunker_bb = []
    async for m in client_prod.iter_messages(bunker_ent, reply_to=TOPIC_BB):
        if m.id != TOPIC_BB and m.file:
            current_bunker_bb.append((m.id, getattr(m.file, 'name', '') or '', m.date))

    # Invertir para ver el orden cronológico en que aparecen en Telegram
    current_bunker_bb.reverse()
    print("=== EPISODIOS EN BÚNKER TOPIC 27949 (ORDEN DE TELEGRAM) ===")
    for idx, (mid, fn, dt) in enumerate(current_bunker_bb, 1):
        print(f"{idx:2d}. [Msg {mid}] {fn}")

    # 2. Ver de dónde salió 6x11 y qué otros archivos hay en Retro y en Comunidad
    print("\n=== BUSCANDO EN COMUNIDAD CASTELLANA (-1002257262928) ===")
    comm_ent = await client_comm.get_entity(COMMUNITY_SERIES)
    comm_bb = []
    async for m in client_comm.iter_messages(comm_ent, search="Breaking Bad", limit=150):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if fn.lower().endswith(('.mkv', '.mp4')):
                comm_bb.append((m.id, fn, parse_episode_sort_key(fn)))

    print(f"Total en Comunidad Castellana: {len(comm_bb)}")
    comm_bb.sort(key=lambda x: x[2])
    for mid, fn, sk in comm_bb[:15]:
        print(f"  T{sk[0]}E{sk[1]}: {fn} (ID {mid})")
    print("  ...")
    for mid, fn, sk in comm_bb[-15:]:
        print(f"  T{sk[0]}E{sk[1]}: {fn} (ID {mid})")

    # 3. Ver en Retro
    print("\n=== BUSCANDO EN RETRO (-1003865750796) ===")
    retro_ent = await client_prod.get_entity(RETRO_SERIES)
    retro_bb = []
    async for m in client_prod.iter_messages(retro_ent, search="Breaking Bad", limit=150):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if fn.lower().endswith(('.mkv', '.mp4')):
                retro_bb.append((m.id, fn, parse_episode_sort_key(fn)))

    print(f"Total en Retro: {len(retro_bb)}")
    retro_bb.sort(key=lambda x: x[2])
    for mid, fn, sk in retro_bb[:15]:
        print(f"  T{sk[0]}E{sk[1]}: {fn} (ID {mid})")
    print("  ...")
    for mid, fn, sk in retro_bb[-15:]:
        print(f"  T{sk[0]}E{sk[1]}: {fn} (ID {mid})")

    await client_prod.disconnect()
    await client_comm.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
