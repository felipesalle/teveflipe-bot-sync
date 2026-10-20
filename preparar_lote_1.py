import asyncio
import os
import re
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetForumTopicsRequest, CreateForumTopicRequest, ForwardMessagesRequest

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")
TELEGRAM_STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION", "")

BUNKER_SERIES = -1002097175258
COMMUNITY_SERIES = -1002257262928
RETRO_SERIES = -1003865750796

def parse_episode_sort_key(filename: str):
    # Patrones comunes: 1x01, S01E01, 1 x 01, S1 E1
    m = re.search(r'(?:(\d{1,2})\s*x\s*(\d{1,2})|[sS](\d{1,2})[._\s]*[eE](\d{1,2}))', filename)
    if m:
        season = int(m.group(1) or m.group(3))
        episode = int(m.group(2) or m.group(4))
        return (season, episode)
    # Patrones 3 o 4 dígitos (ej: 714 -> T7 E14)
    m2 = re.search(r'\b(\d{1,2})(\d{2})\b', filename)
    if m2:
        return (int(m2.group(1)), int(m2.group(2)))
    return (99, 99)

async def main():
    print("🚀 PREPARANDO LOTE 1: BREAKING BAD, MAD MEN, SUCCESSION")
    
    client_prod = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)
    client_comm = TelegramClient(StringSession(TELEGRAM_STRING_SESSION), API_ID, API_HASH)
    await client_prod.connect()
    await client_comm.connect()

    me_prod = await client_prod.get_me()
    me_comm = await client_comm.get_me()
    print(f"Prod: {me_prod.first_name} | Comm: {me_comm.first_name}")

    bunker_ent_prod = await client_prod.get_entity(BUNKER_SERIES)
    comm_ent = await client_comm.get_entity(COMMUNITY_SERIES)

    # 1. Breaking Bad (buscar en Retro y en Comunidad)
    print("\n🔍 Inspeccionando episodios de Breaking Bad...")
    bb_episodes = []
    # Buscar en Retro
    try:
        retro_ent = await client_prod.get_entity(RETRO_SERIES)
        async for m in client_prod.iter_messages(retro_ent, search="Breaking Bad", limit=120):
            if m.file:
                fn = getattr(m.file, 'name', '') or ''
                if fn.lower().endswith(('.mkv', '.mp4')) and 'breaking bad' in fn.lower():
                    bb_episodes.append({
                        "msg_id": m.id,
                        "filename": fn,
                        "sort_key": parse_episode_sort_key(fn),
                        "chat": retro_ent,
                        "client": client_prod
                    })
    except Exception as e:
        print(f"Nota Retro: {e}")

    # Si no en Retro, buscar en Comunidad
    if len(bb_episodes) < 40:
        async for m in client_comm.iter_messages(comm_ent, search="Breaking Bad", limit=120):
            if m.file:
                fn = getattr(m.file, 'name', '') or ''
                if fn.lower().endswith(('.mkv', '.mp4')) and 'breaking bad' in fn.lower():
                    bb_episodes.append({
                        "msg_id": m.id,
                        "filename": fn,
                        "sort_key": parse_episode_sort_key(fn),
                        "chat": comm_ent,
                        "client": client_comm
                    })

    bb_episodes.sort(key=lambda x: x["sort_key"])
    # Deduplicar por sort_key
    unique_bb = []
    seen_bb = set()
    for ep in bb_episodes:
        if ep["sort_key"] not in seen_bb and ep["sort_key"] != (99, 99):
            seen_bb.add(ep["sort_key"])
            unique_bb.append(ep)

    print(f"✅ Breaking Bad: {len(unique_bb)} episodios únicos encontrados.")
    for ep in unique_bb[:3]:
        print(f"   • T{ep['sort_key'][0]}E{ep['sort_key'][1]}: {ep['filename']}")
    print("   ...")
    for ep in unique_bb[-3:]:
        print(f"   • T{ep['sort_key'][0]}E{ep['sort_key'][1]}: {ep['filename']}")

    # 2. Mad Men
    print("\n🔍 Inspeccionando episodios de Mad Men...")
    mm_episodes = []
    async for m in client_comm.iter_messages(comm_ent, search="Mad Men", limit=120):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if fn.lower().endswith(('.mkv', '.mp4')) and 'mad men' in fn.lower():
                mm_episodes.append({
                    "msg_id": m.id,
                    "filename": fn,
                    "sort_key": parse_episode_sort_key(fn),
                    "chat": comm_ent,
                    "client": client_comm
                })

    mm_episodes.sort(key=lambda x: x["sort_key"])
    unique_mm = []
    seen_mm = set()
    for ep in mm_episodes:
        if ep["sort_key"] not in seen_mm and ep["sort_key"] != (99, 99):
            seen_mm.add(ep["sort_key"])
            unique_mm.append(ep)

    print(f"✅ Mad Men: {len(unique_mm)} episodios únicos encontrados.")
    for ep in unique_mm[:3]:
        print(f"   • T{ep['sort_key'][0]}E{ep['sort_key'][1]}: {ep['filename']}")
    print("   ...")
    for ep in unique_mm[-3:]:
        print(f"   • T{ep['sort_key'][0]}E{ep['sort_key'][1]}: {ep['filename']}")

    # 3. Succession
    print("\n🔍 Inspeccionando episodios de Succession...")
    succ_episodes = []
    async for m in client_comm.iter_messages(comm_ent, search="Succession", limit=120):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if fn.lower().endswith(('.mkv', '.mp4')) and ('succession' in fn.lower() or 'succ_' in fn.lower()):
                succ_episodes.append({
                    "msg_id": m.id,
                    "filename": fn,
                    "sort_key": parse_episode_sort_key(fn),
                    "chat": comm_ent,
                    "client": client_comm
                })

    succ_episodes.sort(key=lambda x: x["sort_key"])
    unique_succ = []
    seen_succ = set()
    for ep in succ_episodes:
        if ep["sort_key"] not in seen_succ and ep["sort_key"] != (99, 99):
            seen_succ.add(ep["sort_key"])
            unique_succ.append(ep)

    print(f"✅ Succession: {len(unique_succ)} episodios únicos encontrados.")
    for ep in unique_succ[:3]:
        print(f"   • T{ep['sort_key'][0]}E{ep['sort_key'][1]}: {ep['filename']}")
    print("   ...")
    for ep in unique_succ[-3:]:
        print(f"   • T{ep['sort_key'][0]}E{ep['sort_key'][1]}: {ep['filename']}")

    await client_prod.disconnect()
    await client_comm.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
