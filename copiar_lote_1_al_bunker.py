import asyncio
import os
import sys
import re
import random
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
    m = re.search(r'(?:(\d{1,2})\s*x\s*(\d{1,2})|[sS](\d{1,2})[._\s]*[eE](\d{1,2}))', filename)
    if m:
        season = int(m.group(1) or m.group(3))
        episode = int(m.group(2) or m.group(4))
        return (season, episode)
    m2 = re.search(r'\b(\d{1,2})(\d{2})\b', filename)
    if m2:
        return (int(m2.group(1)), int(m2.group(2)))
    return (99, 99)

async def get_or_create_topic(client, entity, title: str):
    offset_date = None
    offset_id = 0
    offset_topic = 0
    while True:
        res = await client(GetForumTopicsRequest(
            peer=entity,
            offset_date=offset_date,
            offset_id=offset_id,
            offset_topic=offset_topic,
            limit=100
        ))
        for t in res.topics:
            if t.title.strip().lower() == title.strip().lower():
                print(f"📌 Tema existente encontrado en Búnker: '{t.title}' (ID: {t.id})")
                return t.id
        if len(res.topics) < 100:
            break
        last = res.topics[-1]
        offset_topic = last.id
        offset_id = last.top_message
        offset_date = last.date

    # Si no existe, crearlo
    print(f"🆕 Creando nuevo tema en Búnker: '{title}'...")
    created = await client(CreateForumTopicRequest(
        peer=entity,
        title=title,
        random_id=random.randint(1, 2**63 - 1)
    ))
    new_tid = None
    for u in created.updates:
        if hasattr(u, 'id'):
            new_tid = u.id
            break
        if hasattr(u, 'message') and hasattr(u.message, 'action'):
            new_tid = u.message.id
            break
    print(f"✅ Tema creado con Topic ID: {new_tid}")
    return new_tid

async def main():
    print("🚀 INICIANDO COPIA DE LOTE 1 AL BÚNKER SERIES TV")
    client_prod = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)
    client_comm = TelegramClient(StringSession(TELEGRAM_STRING_SESSION), API_ID, API_HASH)

    await client_prod.connect()
    await client_comm.connect()

    bunker_prod = await client_prod.get_entity(BUNKER_SERIES)
    bunker_comm = await client_comm.get_entity(BUNKER_SERIES)
    comm_ent = await client_comm.get_entity(COMMUNITY_SERIES)
    retro_ent = await client_prod.get_entity(RETRO_SERIES)

    # -------------------------------------------------------------
    # SERIE 1: BREAKING BAD
    # -------------------------------------------------------------
    print("\n" + "="*60)
    print("📦 1. PROCESANDO: BREAKING BAD")
    print("="*60)
    topic_bb = await get_or_create_topic(client_prod, bunker_prod, "Breaking Bad")
    
    # Comprobar si ya tiene sinopsis
    has_sinopsis_bb = False
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_bb, limit=10):
        if m.text and "Breaking Bad" in m.text:
            has_sinopsis_bb = True
            break
    if not has_sinopsis_bb:
        sinopsis_bb = (
            "**Breaking Bad** (Serie de TV, 2008–2013)\n\n"
            "• **Temporadas:** 5 (Completa)\n"
            "• **Episodios:** 62\n"
            "• **Calidad:** MKV 1080p MicroHD Castellano\n"
            "• **Género:** Drama, Crimen, Suspense\n\n"
            "**Sinopsis:** Walter White (Bryan Cranston), un frustrado profesor de química de instituto con un hijo "
            "con parálisis cerebral y una mujer embarazada, es diagnosticado de cáncer de pulmón terminal. "
            "Para asegurar el futuro financiero de su familia, decide asociarse con un antiguo alumno, Jesse Pinkman (Aaron Paul), "
            "para fabricar y vender metanfetamina de máxima pureza."
        )
        await client_prod.send_message(bunker_prod, sinopsis_bb, reply_to=topic_bb)

    # Buscar episodios en Retro y en Comunidad
    bb_list = []
    async for m in client_prod.iter_messages(retro_ent, search="Breaking Bad", limit=120):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if fn.lower().endswith(('.mkv', '.mp4')) and 'breaking bad' in fn.lower():
                s_key = parse_episode_sort_key(fn)
                if s_key != (99, 99):
                    bb_list.append({"id": m.id, "fn": fn, "key": s_key, "source": retro_ent, "client": client_prod, "dest": bunker_prod})

    bb_list.sort(key=lambda x: x["key"])
    seen = set()
    unique_bb = [x for x in bb_list if not (x["key"] in seen or seen.add(x["key"]))]

    # Comprobar cuántos ya están en Búnker
    existing_bb = []
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_bb, limit=100):
        if m.file:
            existing_bb.append(m)
    print(f"Breaking Bad: {len(existing_bb)} caps en Búnker | {len(unique_bb)} caps fuente identificados.")

    pending_bb = unique_bb[len(existing_bb):]
    if pending_bb:
        print(f"Reenviando {len(pending_bb)} episodios a Búnker Topic {topic_bb}...")
        for i in range(0, len(pending_bb), 5):
            batch = pending_bb[i:i+5]
            batch_ids = [b["id"] for b in batch]
            await client_prod(ForwardMessagesRequest(
                from_peer=retro_ent,
                to_peer=bunker_prod,
                id=batch_ids,
                top_msg_id=topic_bb,
                drop_author=True
            ))
            print(f"   ✓ Reenviados caps {i+1} a {min(i+5, len(pending_bb))} de {len(pending_bb)}...")
            await asyncio.sleep(2)
    else:
        print("✓ Breaking Bad ya está completa en el Búnker.")

    # -------------------------------------------------------------
    # SERIE 2: MAD MEN
    # -------------------------------------------------------------
    print("\n" + "="*60)
    print("📦 2. PROCESANDO: MAD MEN")
    print("="*60)
    topic_mm = await get_or_create_topic(client_prod, bunker_prod, "Mad Men")
    
    has_sinopsis_mm = False
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_mm, limit=10):
        if m.text and "Mad Men" in m.text:
            has_sinopsis_mm = True
            break
    if not has_sinopsis_mm:
        sinopsis_mm = (
            "**Mad Men** (Serie de TV, 2007–2015)\n\n"
            "• **Temporadas:** 7 (Completa)\n"
            "• **Episodios:** 92\n"
            "• **Calidad:** MP4 720p Castellano\n"
            "• **Género:** Drama, Años 60, Negocios\n\n"
            "**Sinopsis:** En la Nueva York de los años 60, en plena era dorada de la publicidad en Madison Avenue, "
            "Don Draper (Jon Hamm) es el misterioso y brillante director creativo de la agencia Sterling Cooper. "
            "Una crónica implacable del cambio social, la ambición corporativa y la búsqueda de identidad."
        )
        await client_prod.send_message(bunker_prod, sinopsis_mm, reply_to=topic_mm)

    mm_list = []
    async for m in client_comm.iter_messages(comm_ent, search="Mad Men", limit=120):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if fn.lower().endswith(('.mkv', '.mp4')) and 'mad men' in fn.lower():
                s_key = parse_episode_sort_key(fn)
                if s_key != (99, 99):
                    mm_list.append({"id": m.id, "fn": fn, "key": s_key})

    mm_list.sort(key=lambda x: x["key"])
    seen_mm = set()
    unique_mm = [x for x in mm_list if not (x["key"] in seen_mm or seen_mm.add(x["key"]))]

    existing_mm = []
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_mm, limit=120):
        if m.file:
            existing_mm.append(m)
    print(f"Mad Men: {len(existing_mm)} caps en Búnker | {len(unique_mm)} caps fuente identificados.")

    pending_mm = unique_mm[len(existing_mm):]
    if pending_mm:
        print(f"Reenviando {len(pending_mm)} episodios a Búnker Topic {topic_mm}...")
        for i in range(0, len(pending_mm), 5):
            batch = pending_mm[i:i+5]
            batch_ids = [b["id"] for b in batch]
            await client_comm(ForwardMessagesRequest(
                from_peer=comm_ent,
                to_peer=bunker_comm,
                id=batch_ids,
                top_msg_id=topic_mm,
                drop_author=True
            ))
            print(f"   ✓ Reenviados caps {i+1} a {min(i+5, len(pending_mm))} de {len(pending_mm)}...")
            await asyncio.sleep(2)
    else:
        print("✓ Mad Men ya está completa en el Búnker.")

    # -------------------------------------------------------------
    # SERIE 3: SUCCESSION
    # -------------------------------------------------------------
    print("\n" + "="*60)
    print("📦 3. PROCESANDO: SUCCESSION")
    print("="*60)
    topic_succ = await get_or_create_topic(client_prod, bunker_prod, "Succession")

    has_sinopsis_succ = False
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_succ, limit=10):
        if m.text and "Succession" in m.text:
            has_sinopsis_succ = True
            break
    if not has_sinopsis_succ:
        sinopsis_succ = (
            "**Succession** (Serie de TV, 2018–2023)\n\n"
            "• **Temporadas:** 4 (Completa)\n"
            "• **Episodios:** 39\n"
            "• **Calidad:** MKV / MP4 1080p Castellano\n"
            "• **Género:** Drama, Sátira, Negocios, Familia\n\n"
            "**Sinopsis:** Los Roy —Logan y sus cuatro hijos— controlan uno de los mayores conglomerados de medios "
            "y entretenimiento del mundo, Waystar RoyCo. Cuando el envejecido patriarca decide dar un paso atrás, "
            "se desata una despiadada lucha de poder dinástica entre sus ambiciosos herederos."
        )
        await client_prod.send_message(bunker_prod, sinopsis_succ, reply_to=topic_succ)

    succ_list = []
    async for m in client_comm.iter_messages(comm_ent, search="Succession", limit=120):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if fn.lower().endswith(('.mkv', '.mp4')) and ('succession' in fn.lower() or 'succ_' in fn.lower()):
                s_key = parse_episode_sort_key(fn)
                if s_key != (99, 99):
                    succ_list.append({"id": m.id, "fn": fn, "key": s_key})

    succ_list.sort(key=lambda x: x["key"])
    seen_succ = set()
    unique_succ = [x for x in succ_list if not (x["key"] in seen_succ or seen_succ.add(x["key"]))]

    existing_succ = []
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_succ, limit=100):
        if m.file:
            existing_succ.append(m)
    print(f"Succession: {len(existing_succ)} caps en Búnker | {len(unique_succ)} caps fuente identificados.")

    pending_succ = unique_succ[len(existing_succ):]
    if pending_succ:
        print(f"Reenviando {len(pending_succ)} episodios a Búnker Topic {topic_succ}...")
        for i in range(0, len(pending_succ), 5):
            batch = pending_succ[i:i+5]
            batch_ids = [b["id"] for b in batch]
            await client_comm(ForwardMessagesRequest(
                from_peer=comm_ent,
                to_peer=bunker_comm,
                id=batch_ids,
                top_msg_id=topic_succ,
                drop_author=True
            ))
            print(f"   ✓ Reenviados caps {i+1} a {min(i+5, len(pending_succ))} de {len(pending_succ)}...")
            await asyncio.sleep(2)
    else:
        print("✓ Succession ya está completa en el Búnker.")

    print("\n🎉 ¡LOTE 1 COPIADO Y COMPLETADO EXITOSAMENTE AL BÚNKER!")
    await client_prod.disconnect()
    await client_comm.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
