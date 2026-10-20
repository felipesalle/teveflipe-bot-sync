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
    print("🚀 INICIANDO COPIA DE LOTE 4 AL BÚNKER (TRUE DETECTIVE T1, HERMANOS DE SANGRE, BOJACK HORSEMAN)")
    client_prod = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)
    client_comm = TelegramClient(StringSession(TELEGRAM_STRING_SESSION), API_ID, API_HASH)

    await client_prod.connect()
    await client_comm.connect()

    bunker_prod = await client_prod.get_entity(BUNKER_SERIES)
    bunker_comm = await client_comm.get_entity(BUNKER_SERIES)
    comm_ent = await client_comm.get_entity(COMMUNITY_SERIES)

    # -------------------------------------------------------------------------
    # 1. TRUE DETECTIVE (Temporada 1 - 8 episodios)
    # -------------------------------------------------------------------------
    print("\n" + "="*60)
    print("📦 1. PROCESANDO: TRUE DETECTIVE (TEMPORADA 1)")
    print("="*60)
    topic_td = await get_or_create_topic(client_prod, bunker_prod, "True Detective")

    has_sinopsis_td = False
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_td, limit=10):
        if m.text and "True Detective" in m.text:
            has_sinopsis_td = True
            break
    if not has_sinopsis_td:
        sinopsis_td = (
            "**True Detective** (Temporada 1, 2014)\n\n"
            "• **Temporadas:** 1 (Autoconclusiva)\n"
            "• **Episodios:** 8\n"
            "• **Calidad:** MKV 1080p BDRip 10bit x265 Castellano\n"
            "• **Género:** Thriller policiaco, Neo-noir, Misterio gótico sureño\n\n"
            "**Sinopsis:** En 1995, los detectives Rust Cohle (Matthew McConaughey) y Martin Hart (Woody Harrelson), "
            "de la División de Investigaciones Criminales de Luisiana, son asignados al perturbador caso del ritual "
            "homicida de una joven prostituta. Diecisiete años después, ambos son interrogados por separado cuando "
            "un crimen idéntico reabre las heridas no cicatrizadas y los fantasmas del pasado."
        )
        await client_prod.send_message(bunker_prod, sinopsis_td, reply_to=topic_td)

    # Episodios 458064 a 458071 (1x01 a 1x08)
    td_ids = [
        (1, 1, 458064, "True detective 1x01"),
        (1, 2, 458065, "True detective 1x02"),
        (1, 3, 458066, "True detective 1x03"),
        (1, 4, 458067, "True detective 1x04"),
        (1, 5, 458068, "True detective 1x05"),
        (1, 6, 458069, "True detective 1x06"),
        (1, 7, 458070, "True detective 1x07"),
        (1, 8, 458071, "True detective 1x08"),
    ]

    existing_td = []
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_td):
        if m.id != topic_td and m.file:
            existing_td.append(m)

    print(f"True Detective: {len(existing_td)} archivos en Búnker | 8 identificados.")
    if len(existing_td) < len(td_ids):
        print("Reenviando 8 episodios uno a uno en orden cronológico estricto...")
        for idx, (s, e, mid, fn) in enumerate(td_ids, 1):
            await client_comm(ForwardMessagesRequest(
                from_peer=comm_ent,
                to_peer=bunker_comm,
                id=[mid],
                top_msg_id=topic_td,
                drop_author=True
            ))
            print(f"   [{idx:02d}/08] Reenviado S{s:02d}E{e:02d}: {fn}")
            await asyncio.sleep(1.2)
        print("✓ True Detective completada con éxito.")
    else:
        print("✓ True Detective ya está completa en el Búnker.")

    # -------------------------------------------------------------------------
    # 2. HERMANOS DE SANGRE (Band of Brothers - 10 episodios)
    # -------------------------------------------------------------------------
    print("\n" + "="*60)
    print("📦 2. PROCESANDO: HERMANOS DE SANGRE (BAND OF BROTHERS)")
    print("="*60)
    topic_bob = await get_or_create_topic(client_prod, bunker_prod, "Hermanos de Sangre (Band of Brothers)")

    has_sinopsis_bob = False
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_bob, limit=10):
        if m.text and ("Hermanos de Sangre" in m.text or "Band of Brothers" in m.text):
            has_sinopsis_bob = True
            break
    if not has_sinopsis_bob:
        sinopsis_bob = (
            "**Hermanos de Sangre (Band of Brothers)** (Miniserie de TV, 2001)\n\n"
            "• **Temporadas:** 1 (Miniserie Completa)\n"
            "• **Episodios:** 10 (+ Extras)\n"
            "• **Calidad:** MKV 1080p Castellano\n"
            "• **Género:** Bélico, Histórico, Acción, Drama\n\n"
            "**Sinopsis:** Producida por Steven Spielberg y Tom Hanks, es considerada el estándar de oro "
            "del drama bélico televisivo. Sigue la historia real de la Compañía Easy del 506º Regimiento "
            "de Infantería Paracaidista del Ejército de los EE. UU., desde su duro entrenamiento inicial "
            "hasta el desembarco de Normandía, la Operación Market Garden, la Batalla de las Ardenas y la captura "
            "del Nido del Águila de Hitler."
        )
        await client_prod.send_message(bunker_prod, sinopsis_bob, reply_to=topic_bob)

    # Episodios 282093 a 282103 (1x01 a 1x10 + Extras)
    bob_ids = [
        (1, 1, 282093, "Hermanos de Sangre 1x01"),
        (1, 2, 282094, "Hermanos de Sangre 1x02"),
        (1, 3, 282095, "Hermanos de Sangre 1x03"),
        (1, 4, 282096, "Hermanos de Sangre 1x04"),
        (1, 5, 282097, "Hermanos de Sangre 1x05"),
        (1, 6, 282098, "Hermanos de Sangre 1x06"),
        (1, 7, 282099, "Hermanos de Sangre 1x07"),
        (1, 8, 282100, "Hermanos de Sangre 1x08"),
        (1, 9, 282101, "Hermanos de Sangre 1x09"),
        (1, 10, 282102, "Hermanos de Sangre 1x10"),
        (1, 99, 282103, "Hermanos de Sangre Extras"),
    ]

    existing_bob = []
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_bob):
        if m.id != topic_bob and m.file:
            existing_bob.append(m)

    print(f"Hermanos de Sangre: {len(existing_bob)} archivos en Búnker | {len(bob_ids)} identificados.")
    if len(existing_bob) < len(bob_ids):
        print("Reenviando episodios uno a uno en orden cronológico estricto...")
        for idx, (s, e, mid, fn) in enumerate(bob_ids, 1):
            await client_comm(ForwardMessagesRequest(
                from_peer=comm_ent,
                to_peer=bunker_comm,
                id=[mid],
                top_msg_id=topic_bob,
                drop_author=True
            ))
            print(f"   [{idx:02d}/11] Reenviado S{s:02d}E{e:02d}: {fn}")
            await asyncio.sleep(1.2)
        print("✓ Hermanos de Sangre completada con éxito.")
    else:
        print("✓ Hermanos de Sangre ya está completa en el Búnker.")

    # -------------------------------------------------------------------------
    # 3. BOJACK HORSEMAN (6 temporadas - 76 episodios)
    # -------------------------------------------------------------------------
    print("\n" + "="*60)
    print("📦 3. PROCESANDO: BOJACK HORSEMAN")
    print("="*60)
    topic_bj = await get_or_create_topic(client_prod, bunker_prod, "BoJack Horseman")

    has_sinopsis_bj = False
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_bj, limit=10):
        if m.text and "BoJack Horseman" in m.text:
            has_sinopsis_bj = True
            break
    if not has_sinopsis_bj:
        sinopsis_bj = (
            "**BoJack Horseman** (Serie de TV de Animación, 2014–2020)\n\n"
            "• **Temporadas:** 6 (Completa)\n"
            "• **Episodios:** 76\n"
            "• **Calidad:** MKV 1080p Castellano\n"
            "• **Género:** Animación para adultos, Comedia dramática, Sátira, Existencialismo\n\n"
            "**Sinopsis:** En un Hollywood surrealista donde humanos y animales antropomórficos conviven, "
            "BoJack Horseman —antigua estrella equina de la exitosa comedia noventera 'Horsin' Around'— "
            "lidia con su propia autodestrucción, depresión, adicciones y cinismo existencial en un intento "
            "desesperado por volver a ser relevante y redimirse ante quienes lo rodean."
        )
        await client_prod.send_message(bunker_prod, sinopsis_bj, reply_to=topic_bj)

    # Recolectar episodios de BoJack Horseman
    bj_files = []
    async for m in client_comm.iter_messages(comm_ent, search="BoJack Horseman", limit=160):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if fn.lower().endswith(('.mkv', '.mp4')) and 'bojack horseman' in fn.lower():
                s, e = parse_episode_sort_key(fn)
                if 1 <= s <= 6 and 1 <= e <= 16:
                    bj_files.append((s, e, m.id, fn, m.file.size))

    by_ep_bj = {}
    for s, e, mid, fn, sz in bj_files:
        by_ep_bj.setdefault((s, e), []).append((mid, fn, sz))

    selected_bj = {}
    expected_bj = {1: 12, 2: 12, 3: 12, 4: 12, 5: 12, 6: 16}
    for s, max_e in expected_bj.items():
        for e in range(1, max_e + 1):
            variants = by_ep_bj.get((s, e), [])
            if variants:
                best = sorted(variants, key=lambda x: (1 if '1080' in x[1] else 0, x[2]), reverse=True)[0]
                selected_bj[(s, e)] = best

    existing_bj = []
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_bj):
        if m.id != topic_bj and m.file:
            existing_bj.append(m)

    print(f"BoJack Horseman: {len(existing_bj)} archivos en Búnker | {len(selected_bj)} identificados.")
    if len(existing_bj) < len(selected_bj):
        print(f"Reenviando {len(selected_bj)} episodios uno a uno en orden cronológico estricto...")
        sorted_keys = sorted(selected_bj.keys())
        for idx, (s, e) in enumerate(sorted_keys, 1):
            mid, fn, sz = selected_bj[(s, e)]
            await client_comm(ForwardMessagesRequest(
                from_peer=comm_ent,
                to_peer=bunker_comm,
                id=[mid],
                top_msg_id=topic_bj,
                drop_author=True
            ))
            print(f"   [{idx:02d}/{len(sorted_keys)}] Reenviado S{s:02d}E{e:02d}: {fn}")
            await asyncio.sleep(1.2)
        print("✓ BoJack Horseman completada con éxito.")
    else:
        print("✓ BoJack Horseman ya está completa en el Búnker.")

    print("\n🎉 ¡LOTE 4 TRANSFERIDO Y COMPLETADO CON ÉXITO AL BÚNKER!")
    await client_prod.disconnect()
    await client_comm.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
