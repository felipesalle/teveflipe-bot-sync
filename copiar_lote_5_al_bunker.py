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
    print("🚀 INICIANDO COPIA DE LOTE 5 AL BÚNKER (THE WIRE, SEVERANCE, ANDOR)")
    client_prod = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)
    client_comm = TelegramClient(StringSession(TELEGRAM_STRING_SESSION), API_ID, API_HASH)

    await client_prod.connect()
    await client_comm.connect()

    bunker_prod = await client_prod.get_entity(BUNKER_SERIES)
    bunker_comm = await client_comm.get_entity(BUNKER_SERIES)
    comm_ent = await client_comm.get_entity(COMMUNITY_SERIES)

    # -------------------------------------------------------------------------
    # 1. THE WIRE (Bajo Escucha - 60 episodios)
    # -------------------------------------------------------------------------
    print("\n" + "="*60)
    print("📦 1. PROCESANDO: THE WIRE (BAJO ESCUCHA)")
    print("="*60)
    topic_tw = await get_or_create_topic(client_prod, bunker_prod, "The Wire (Bajo Escucha)")

    has_sinopsis_tw = False
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_tw, limit=10):
        if m.text and ("The Wire" in m.text or "Bajo Escucha" in m.text):
            has_sinopsis_tw = True
            break
    if not has_sinopsis_tw:
        sinopsis_tw = (
            "**The Wire (Bajo Escucha)** (Serie de TV, 2002–2008)\n\n"
            "• **Temporadas:** 5 (Completa)\n"
            "• **Episodios:** 60\n"
            "• **Calidad:** MKV 1080p Castellano\n"
            "• **Género:** Drama policial, Crimen, Sociológico, Política\n\n"
            "**Sinopsis:** Obra cumbre de David Simon considerada por la crítica universal como la mejor "
            "serie de televisión de todos los tiempos. Un implacable fresco sociológico sobre Baltimore "
            "y las contradicciones del sistema estadounidense a través de 5 perspectivas interconectadas: "
            "el narcotráfico callejero, el declive de los estibadores portuarios, el aparato político municipal, "
            "el sistema escolar y el papel de la prensa escrita."
        )
        await client_prod.send_message(bunker_prod, sinopsis_tw, reply_to=topic_tw)

    # Pack completo de The Wire (mensajes 421941 a 422004)
    # T1: 421941 - 421953 (13 caps)
    # T2: 421955 - 421966 (12 caps)
    # T3: 421968 - 421979 (12 caps)
    # T4: 421981 - 421993 (13 caps)
    # T5: 421995 - 422004 (10 caps)
    tw_ranges = [
        (1, list(range(421941, 421954))),
        (2, list(range(421955, 421967))),
        (3, list(range(421968, 421980))),
        (4, list(range(421981, 421994))),
        (5, list(range(421995, 422005))),
    ]
    tw_ids = []
    for s, m_ids in tw_ranges:
        for ep_idx, mid in enumerate(m_ids, 1):
            tw_ids.append((s, ep_idx, mid))

    existing_tw = []
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_tw):
        if m.id != topic_tw and m.file:
            existing_tw.append(m)

    print(f"The Wire: {len(existing_tw)} archivos en Búnker | {len(tw_ids)} identificados.")
    if len(existing_tw) < len(tw_ids):
        print("Reenviando 60 episodios uno a uno en orden cronológico estricto...")
        for idx, (s, e, mid) in enumerate(tw_ids, 1):
            await client_comm(ForwardMessagesRequest(
                from_peer=comm_ent,
                to_peer=bunker_comm,
                id=[mid],
                top_msg_id=topic_tw,
                drop_author=True
            ))
            print(f"   [{idx:02d}/60] Reenviado S{s:02d}E{e:02d} (msg {mid})")
            await asyncio.sleep(1.2)
        print("✓ The Wire completada con éxito.")
    else:
        print("✓ The Wire ya está completa en el Búnker.")

    # -------------------------------------------------------------------------
    # 2. SEVERANCE (Separación - 9 episodios)
    # -------------------------------------------------------------------------
    print("\n" + "="*60)
    print("📦 2. PROCESANDO: SEVERANCE (SEPARACIÓN)")
    print("="*60)
    topic_sev = await get_or_create_topic(client_prod, bunker_prod, "Severance (Separación)")

    has_sinopsis_sev = False
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_sev, limit=10):
        if m.text and ("Severance" in m.text or "Separación" in m.text):
            has_sinopsis_sev = True
            break
    if not has_sinopsis_sev:
        sinopsis_sev = (
            "**Severance (Separación)** (Serie de TV, 2022–)\n\n"
            "• **Temporadas:** 1 (Temporada 1 Completa)\n"
            "• **Episodios:** 9\n"
            "• **Calidad:** MKV 4K UHD Castellano\n"
            "• **Género:** Ciencia ficción, Thriller psicológico, Distopía laboral\n\n"
            "**Sinopsis:** Mark Scout (Adam Scott) lidera un equipo en Lumon Industries, donde los empleados "
            "se someten a un procedimiento quirúrgico de separación que divide quirúrgicamente los recuerdos "
            "entre el trabajo y la vida personal. Este audaz experimento de conciliación laboral se pone en tela de juicio "
            "cuando Mark se ve envuelto en una red de misterios que le obligará a confrontar la verdadera naturaleza de su empleo."
        )
        await client_prod.send_message(bunker_prod, sinopsis_sev, reply_to=topic_sev)

    # Mensajes 411427 a 411435 (1x01 a 1x09 en 4K UHD)
    sev_ids = [
        (1, idx, mid) for idx, mid in enumerate(range(411427, 411436), 1)
    ]

    existing_sev = []
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_sev):
        if m.id != topic_sev and m.file:
            existing_sev.append(m)

    print(f"Severance: {len(existing_sev)} archivos en Búnker | {len(sev_ids)} identificados.")
    if len(existing_sev) < len(sev_ids):
        print("Reenviando 9 episodios uno a uno en orden cronológico estricto...")
        for idx, (s, e, mid) in enumerate(sev_ids, 1):
            await client_comm(ForwardMessagesRequest(
                from_peer=comm_ent,
                to_peer=bunker_comm,
                id=[mid],
                top_msg_id=topic_sev,
                drop_author=True
            ))
            print(f"   [{idx:02d}/09] Reenviado S{s:02d}E{e:02d} (msg {mid})")
            await asyncio.sleep(1.2)
        print("✓ Severance completada con éxito.")
    else:
        print("✓ Severance ya está completa en el Búnker.")

    # -------------------------------------------------------------------------
    # 3. ANDOR (Star Wars: Andor - 12 episodios)
    # -------------------------------------------------------------------------
    print("\n" + "="*60)
    print("📦 3. PROCESANDO: ANDOR (STAR WARS: ANDOR)")
    print("="*60)
    topic_andor = await get_or_create_topic(client_prod, bunker_prod, "Andor (Star Wars: Andor)")

    has_sinopsis_andor = False
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_andor, limit=10):
        if m.text and "Andor" in m.text:
            has_sinopsis_andor = True
            break
    if not has_sinopsis_andor:
        sinopsis_andor = (
            "**Star Wars: Andor** (Serie de TV, 2022–)\n\n"
            "• **Temporadas:** 1 (Temporada 1 Completa)\n"
            "• **Episodios:** 12\n"
            "• **Calidad:** MKV 1080p 10bit x265 Castellano\n"
            "• **Género:** Ciencia ficción, Thriller de espionaje, Acción, Drama político\n\n"
            "**Sinopsis:** Precuela de 'Rogue One' aclamada como la cúspide artística de la franquicia Star Wars. "
            "Sigue el despertar político y la transformación de Cassian Andor (Diego Luna) de un cínico ladrón marginal "
            "a un comprometido agente revolucionario, explorando con madurez, realismo y asfixiante tensión el implacable "
            "control del Imperio Galáctico y el enorme costo personal que exige encender la rebelión."
        )
        await client_prod.send_message(bunker_prod, sinopsis_andor, reply_to=topic_andor)

    # Mensajes 161991 a 162002 (1x01 a 1x12 en 1080p 10bit x265)
    andor_ids = [
        (1, idx, mid) for idx, mid in enumerate(range(161991, 162003), 1)
    ]

    existing_andor = []
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_andor):
        if m.id != topic_andor and m.file:
            existing_andor.append(m)

    print(f"Andor: {len(existing_andor)} archivos en Búnker | {len(andor_ids)} identificados.")
    if len(existing_andor) < len(andor_ids):
        print("Reenviando 12 episodios uno a uno en orden cronológico estricto...")
        for idx, (s, e, mid) in enumerate(andor_ids, 1):
            await client_comm(ForwardMessagesRequest(
                from_peer=comm_ent,
                to_peer=bunker_comm,
                id=[mid],
                top_msg_id=topic_andor,
                drop_author=True
            ))
            print(f"   [{idx:02d}/12] Reenviado S{s:02d}E{e:02d} (msg {mid})")
            await asyncio.sleep(1.2)
        print("✓ Andor completada con éxito.")
    else:
        print("✓ Andor ya está completa en el Búnker.")

    print("\n🎉 ¡LOTE 5 TRANSFERIDO Y COMPLETADO CON ÉXITO AL BÚNKER!")
    await client_prod.disconnect()
    await client_comm.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
