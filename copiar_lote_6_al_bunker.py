import asyncio
import os
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
    print("🚀 INICIANDO COPIA DE LOTE 6 AL BÚNKER (PERDIDOS / LOST Y FARGO)")
    client_prod = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)
    client_comm = TelegramClient(StringSession(TELEGRAM_STRING_SESSION), API_ID, API_HASH)

    await client_prod.connect()
    await client_comm.connect()

    bunker_prod = await client_prod.get_entity(BUNKER_SERIES)
    bunker_comm = await client_comm.get_entity(BUNKER_SERIES)
    comm_ent = await client_comm.get_entity(COMMUNITY_SERIES)

    # -------------------------------------------------------------------------
    # 1. FARGO (Temporadas 1 a 4 - 41 episodios)
    # -------------------------------------------------------------------------
    print("\n" + "="*60)
    print("📦 1. PROCESANDO: FARGO")
    print("="*60)
    topic_fargo = await get_or_create_topic(client_prod, bunker_prod, "Fargo")

    has_sinopsis_fargo = False
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_fargo, limit=10):
        if m.text and "Fargo" in m.text:
            has_sinopsis_fargo = True
            break
    if not has_sinopsis_fargo:
        sinopsis_fargo = (
            "**Fargo** (Serie de TV, 2014–)\n\n"
            "• **Temporadas:** 4 (Completas)\n"
            "• **Episodios:** 41\n"
            "• **Calidad:** MKV 1080p HEVC x265 Castellano\n"
            "• **Género:** Thriller, Crimen, Comedia negra, Neo-noir\n\n"
            "**Sinopsis:** Antología criminal inspirada en el universo cinematográfico de los hermanos Coen. "
            "Cada temporada presenta una historia autoconclusiva con nuevos personajes, épocas y escenarios, "
            "pero manteniendo el inconfundible humor negro, la violencia absurda y los giros del destino en el "
            "frío y desolado paisaje de Minnesota y Dakota del Norte."
        )
        await client_prod.send_message(bunker_prod, sinopsis_fargo, reply_to=topic_fargo)

    # Recopilar episodios de Fargo ordenados
    fargo_files = {}
    async for m in client_comm.iter_messages(comm_ent, min_id=458000, max_id=458050):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            s, e = parse_episode_sort_key(fn)
            if s != 99 and fn.lower().endswith(('.mkv', '.mp4')) and 'fargo' in fn.lower():
                fargo_files[(s, e)] = m.id

    fargo_keys = sorted(fargo_files.keys())
    existing_fargo = []
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_fargo):
        if m.id != topic_fargo and m.file:
            existing_fargo.append(m)

    print(f"Fargo: {len(existing_fargo)} archivos en Búnker | {len(fargo_keys)} identificados.")
    if len(existing_fargo) < len(fargo_keys):
        print("Reenviando 41 episodios de Fargo uno a uno en orden cronológico estricto...")
        for idx, (s, e) in enumerate(fargo_keys, 1):
            mid = fargo_files[(s, e)]
            await client_comm(ForwardMessagesRequest(
                from_peer=comm_ent,
                to_peer=bunker_comm,
                id=[mid],
                top_msg_id=topic_fargo,
                drop_author=True
            ))
            print(f"   [{idx:02d}/{len(fargo_keys)}] Reenviado S{s:02d}E{e:02d} (msg {mid})")
            await asyncio.sleep(1.2)
        print("✓ Fargo completada con éxito.")
    else:
        print("✓ Fargo ya está completa en el Búnker.")

    # -------------------------------------------------------------------------
    # 2. PERDIDOS (LOST - 6 Temporadas completas - 119 episodios)
    # -------------------------------------------------------------------------
    print("\n" + "="*60)
    print("📦 2. PROCESANDO: PERDIDOS (LOST)")
    print("="*60)
    topic_lost = await get_or_create_topic(client_prod, bunker_prod, "Perdidos (Lost)")

    has_sinopsis_lost = False
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_lost, limit=10):
        if m.text and ("Perdidos" in m.text or "Lost" in m.text):
            has_sinopsis_lost = True
            break
    if not has_sinopsis_lost:
        sinopsis_lost = (
            "**Perdidos (Lost)** (Serie de TV, 2004–2010)\n\n"
            "• **Temporadas:** 6 (Completa)\n"
            "• **Episodios:** 119 (Serie completa oficial con pilotos/finales dobles integrados)\n"
            "• **Calidad:** MKV 1080p Castellano\n"
            "• **Género:** Intriga, Aventura, Ciencia ficción, Drama, Misterio\n\n"
            "**Sinopsis:** El vuelo 815 de Oceanic Air se estrella en una misteriosa isla del Pacífico aparentemente "
            "desierta. Los 48 supervivientes deberán aprender a cooperar no solo para sobrevivir a las adversidades "
            "del terreno, sino frente a oscuros enigmas: el Monstruo de Humo, la Iniciativa Dharma, Los Otros y los "
            "secretos de sus propias vidas pasadas que los unen inexorablemente al destino de la isla."
        )
        await client_prod.send_message(bunker_prod, sinopsis_lost, reply_to=topic_lost)

    # Recopilar episodios de Lost ordenados
    lost_files = {}
    async for m in client_comm.iter_messages(comm_ent, min_id=572730, max_id=572865):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if fn.lower().endswith(('.mkv', '.mp4')) and ('perdidos' in fn.lower() or 'lost' in fn.lower()):
                s, e = parse_episode_sort_key(fn)
                if s != 99:
                    lost_files[(s, e)] = m.id

    lost_keys = sorted(lost_files.keys())
    existing_lost = []
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_lost):
        if m.id != topic_lost and m.file:
            existing_lost.append(m)

    print(f"Perdidos (Lost): {len(existing_lost)} archivos en Búnker | {len(lost_keys)} identificados.")
    if len(existing_lost) < len(lost_keys):
        print(f"Reenviando {len(lost_keys)} episodios de Lost uno a uno en orden cronológico estricto...")
        for idx, (s, e) in enumerate(lost_keys, 1):
            mid = lost_files[(s, e)]
            await client_comm(ForwardMessagesRequest(
                from_peer=comm_ent,
                to_peer=bunker_comm,
                id=[mid],
                top_msg_id=topic_lost,
                drop_author=True
            ))
            if idx % 10 == 0 or idx == len(lost_keys):
                print(f"   [{idx:03d}/{len(lost_keys)}] Reenviado S{s:02d}E{e:02d} (msg {mid})")
            await asyncio.sleep(1.2)
        print("✓ Perdidos (Lost) completada con éxito.")
    else:
        print("✓ Perdidos (Lost) ya está completa en el Búnker.")

    await client_comm.disconnect()
    await client_prod.disconnect()
    print("\n🎉 LOTE 6 FINALIZADO CON ÉXITO.")

if __name__ == "__main__":
    asyncio.run(main())
