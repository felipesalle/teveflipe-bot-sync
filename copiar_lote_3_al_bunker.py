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
    print("🚀 INICIANDO COPIA DE LOTE 3 AL BÚNKER (FLEABAG, GAMBITO DE DAMA, ARCANE)")
    client_prod = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)
    client_comm = TelegramClient(StringSession(TELEGRAM_STRING_SESSION), API_ID, API_HASH)

    await client_prod.connect()
    await client_comm.connect()

    bunker_prod = await client_prod.get_entity(BUNKER_SERIES)
    bunker_comm = await client_comm.get_entity(BUNKER_SERIES)
    comm_ent = await client_comm.get_entity(COMMUNITY_SERIES)

    # -------------------------------------------------------------------------
    # 1. FLEABAG (12 episodios)
    # -------------------------------------------------------------------------
    print("\n" + "="*60)
    print("📦 1. PROCESANDO: FLEABAG")
    print("="*60)
    topic_fb = await get_or_create_topic(client_prod, bunker_prod, "Fleabag")

    has_sinopsis_fb = False
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_fb, limit=10):
        if m.text and "Fleabag" in m.text:
            has_sinopsis_fb = True
            break
    if not has_sinopsis_fb:
        sinopsis_fb = (
            "**Fleabag** (Serie de TV, 2016–2019)\n\n"
            "• **Temporadas:** 2 (Completa)\n"
            "• **Episodios:** 12\n"
            "• **Calidad:** MKV 1080p Castellano\n"
            "• **Género:** Comedia ácida, Drama, Romance\n\n"
            "**Sinopsis:** Creada y protagonizada por Phoebe Waller-Bridge, narra las desventuras "
            "sentimentales, familiares y existenciales de una mujer mordaz, vulnerable e inconformista "
            "que intenta superar el dolor y el duelo mientras rompe continuamente la cuarta pared "
            "para interpelar con ironía y complicidad al espectador."
        )
        await client_prod.send_message(bunker_prod, sinopsis_fb, reply_to=topic_fb)

    # Episodios identificados con certeza absoluta
    # T1: 294390 a 294395 (1x01 a 1x06)
    # T2: 294397 a 294402 (2x01 a 2x06)
    fb_ids = [
        (1, 1, 294390, "Fleabag 1x01.mkv"),
        (1, 2, 294391, "Fleabag 1x02.mkv"),
        (1, 3, 294392, "Fleabag 1x03.mkv"),
        (1, 4, 294393, "Fleabag 1x04.mkv"),
        (1, 5, 294394, "Fleabag 1x05.mkv"),
        (1, 6, 294395, "Fleabag 1x06.mkv"),
        (2, 1, 294397, "Fleabag 2x01.mkv"),
        (2, 2, 294398, "Fleabag 2x02.mkv"),
        (2, 3, 294399, "Fleabag 2x03.mkv"),
        (2, 4, 294400, "Fleabag 2x04.mkv"),
        (2, 5, 294401, "Fleabag 2x05.mkv"),
        (2, 6, 294402, "Fleabag 2x06.mkv"),
    ]

    existing_fb = []
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_fb):
        if m.id != topic_fb and m.file:
            existing_fb.append(m)

    print(f"Fleabag: {len(existing_fb)} archivos en Búnker | 12 identificados.")
    if len(existing_fb) < len(fb_ids):
        print(f"Reenviando 12 episodios uno a uno en orden cronológico estricto...")
        for idx, (s, e, mid, fn) in enumerate(fb_ids, 1):
            await client_comm(ForwardMessagesRequest(
                from_peer=comm_ent,
                to_peer=bunker_comm,
                id=[mid],
                top_msg_id=topic_fb,
                drop_author=True
            ))
            print(f"   [{idx:02d}/12] Reenviado S{s:02d}E{e:02d}: {fn}")
            await asyncio.sleep(1.2)
        print("✓ Fleabag completada con éxito.")
    else:
        print("✓ Fleabag ya está completa en el Búnker.")

    # -------------------------------------------------------------------------
    # 2. GAMBITO DE DAMA (7 episodios)
    # -------------------------------------------------------------------------
    print("\n" + "="*60)
    print("📦 2. PROCESANDO: GAMBITO DE DAMA")
    print("="*60)
    topic_gd = await get_or_create_topic(client_prod, bunker_prod, "Gambito de Dama")

    has_sinopsis_gd = False
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_gd, limit=10):
        if m.text and "Gambito de Dama" in m.text:
            has_sinopsis_gd = True
            break
    if not has_sinopsis_gd:
        sinopsis_gd = (
            "**Gambito de Dama** (Miniserie de TV, 2020)\n\n"
            "• **Temporadas:** 1 (Miniserie Completa)\n"
            "• **Episodios:** 7\n"
            "• **Calidad:** MKV 1080p Castellano\n"
            "• **Género:** Drama, Ajedrez, Época\n\n"
            "**Sinopsis:** En plena Guerra Fría, Beth Harmon (Anya Taylor-Joy), una huérfana tímida y solitaria, "
            "descubre en un orfanato de Kentucky su asombroso talento para el ajedrez. Mientras lucha contra sus "
            "adicciones y las barreras de un mundo dominado por hombres, inicia una fulgurante carrera internacional "
            "hacia la cima del ajedrez mundial."
        )
        await client_prod.send_message(bunker_prod, sinopsis_gd, reply_to=topic_gd)

    # Episodios 211751 a 211757
    gd_ids = [
        (1, 1, 211751, "1x01 - Gambito de Dama.mkv"),
        (1, 2, 211752, "1x02 - Gambito de Dama.mkv"),
        (1, 3, 211753, "1x03 - Gambito de Dama.mkv"),
        (1, 4, 211754, "1x04 - Gambito de Dama.mkv"),
        (1, 5, 211755, "1x05 - Gambito de Dama.mkv"),
        (1, 6, 211756, "1x06 - Gambito de Dama.mkv"),
        (1, 7, 211757, "1x07 - Gambito de Dama.mkv"),
    ]

    existing_gd = []
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_gd):
        if m.id != topic_gd and m.file:
            existing_gd.append(m)

    print(f"Gambito de Dama: {len(existing_gd)} archivos en Búnker | 7 identificados.")
    if len(existing_gd) < len(gd_ids):
        print(f"Reenviando 7 episodios uno a uno en orden cronológico estricto...")
        for idx, (s, e, mid, fn) in enumerate(gd_ids, 1):
            await client_comm(ForwardMessagesRequest(
                from_peer=comm_ent,
                to_peer=bunker_comm,
                id=[mid],
                top_msg_id=topic_gd,
                drop_author=True
            ))
            print(f"   [{idx:02d}/07] Reenviado S{s:02d}E{e:02d}: {fn}")
            await asyncio.sleep(1.2)
        print("✓ Gambito de Dama completada con éxito.")
    else:
        print("✓ Gambito de Dama ya está completa en el Búnker.")

    # -------------------------------------------------------------------------
    # 3. ARCANE (18 episodios)
    # -------------------------------------------------------------------------
    print("\n" + "="*60)
    print("📦 3. PROCESANDO: ARCANE")
    print("="*60)
    topic_arc = await get_or_create_topic(client_prod, bunker_prod, "Arcane")

    has_sinopsis_arc = False
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_arc, limit=10):
        if m.text and "Arcane" in m.text:
            has_sinopsis_arc = True
            break
    if not has_sinopsis_arc:
        sinopsis_arc = (
            "**Arcane** (Serie de TV de Animación, 2021–2024)\n\n"
            "• **Temporadas:** 2 (Completa)\n"
            "• **Episodios:** 18\n"
            "• **Calidad:** MKV 1080p Netflix Castellano\n"
            "• **Género:** Animación, Fantasía, Ciencia ficción, Acción, Drama\n\n"
            "**Sinopsis:** Obra cumbre de la animación contemporánea ambientada en el universo de League of Legends. "
            "Narra el violento conflicto de clases entre la opulenta y tecnológica ciudad de Piltover y los bajos fondos "
            "oprimidos de Zaun, entrelazado con la trágica separación de dos hermanas unidas por el destino y enfrentadas "
            "por la guerra: Vi y Jinx."
        )
        await client_prod.send_message(bunker_prod, sinopsis_arc, reply_to=topic_arc)

    # T1: 425835 a 425843 (9 caps)
    # T2: 313033 a 313041 (9 caps)
    arc_ids = [
        (1, 1, 425835, "Arcane S01E01"),
        (1, 2, 425836, "Arcane S01E02"),
        (1, 3, 425837, "Arcane S01E03"),
        (1, 4, 425838, "Arcane S01E04"),
        (1, 5, 425839, "Arcane S01E05"),
        (1, 6, 425840, "Arcane S01E06"),
        (1, 7, 425841, "Arcane S01E07"),
        (1, 8, 425842, "Arcane S01E08"),
        (1, 9, 425843, "Arcane S01E09"),
        (2, 1, 313033, "Arcane S02E01"),
        (2, 2, 313034, "Arcane S02E02"),
        (2, 3, 313035, "Arcane S02E03"),
        (2, 4, 313036, "Arcane S02E04"),
        (2, 5, 313037, "Arcane S02E05"),
        (2, 6, 313038, "Arcane S02E06"),
        (2, 7, 313039, "Arcane S02E07"),
        (2, 8, 313040, "Arcane S02E08"),
        (2, 9, 313041, "Arcane S02E09"),
    ]

    existing_arc = []
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_arc):
        if m.id != topic_arc and m.file:
            existing_arc.append(m)

    print(f"Arcane: {len(existing_arc)} archivos en Búnker | 18 identificados.")
    if len(existing_arc) < len(arc_ids):
        print(f"Reenviando 18 episodios uno a uno en orden cronológico estricto...")
        for idx, (s, e, mid, fn) in enumerate(arc_ids, 1):
            await client_comm(ForwardMessagesRequest(
                from_peer=comm_ent,
                to_peer=bunker_comm,
                id=[mid],
                top_msg_id=topic_arc,
                drop_author=True
            ))
            print(f"   [{idx:02d}/18] Reenviado S{s:02d}E{e:02d}: {fn}")
            await asyncio.sleep(1.2)
        print("✓ Arcane completada con éxito.")
    else:
        print("✓ Arcane ya está completa en el Búnker.")

    print("\n🎉 ¡LOTE 3 TRANSFERIDO Y COMPLETADO CON ÉXITO AL BÚNKER!")
    await client_prod.disconnect()
    await client_comm.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
