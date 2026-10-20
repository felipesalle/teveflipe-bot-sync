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
    print("🚀 INICIANDO COPIA DE LOTE 2 AL BÚNKER (PEAKY BLINDERS, BLACK MIRROR, CHERNOBYL)")
    client_prod = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)
    client_comm = TelegramClient(StringSession(TELEGRAM_STRING_SESSION), API_ID, API_HASH)

    await client_prod.connect()
    await client_comm.connect()

    bunker_prod = await client_prod.get_entity(BUNKER_SERIES)
    bunker_comm = await client_comm.get_entity(BUNKER_SERIES)
    comm_ent = await client_comm.get_entity(COMMUNITY_SERIES)

    # -------------------------------------------------------------------------
    # 1. PEAKY BLINDERS
    # -------------------------------------------------------------------------
    print("\n" + "="*60)
    print("📦 1. PROCESANDO: PEAKY BLINDERS")
    print("="*60)
    topic_pb = await get_or_create_topic(client_prod, bunker_prod, "Peaky Blinders")

    # Sinopsis
    has_sinopsis_pb = False
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_pb, limit=10):
        if m.text and "Peaky Blinders" in m.text:
            has_sinopsis_pb = True
            break
    if not has_sinopsis_pb:
        sinopsis_pb = (
            "**Peaky Blinders** (Serie de TV, 2013–2022)\n\n"
            "• **Temporadas:** 6 (Completa)\n"
            "• **Episodios:** 36\n"
            "• **Calidad:** MKV 1080p Castellano\n"
            "• **Género:** Drama, Crimen, Histórico, Suspense\n\n"
            "**Sinopsis:** En la Inglaterra de entreguerras tras la Primera Guerra Mundial, "
            "Thomas Shelby (Cillian Murphy) y sus hermanos regresan a Birmingham para liderar "
            "la banda criminal conocida como los Peaky Blinders, caracterizados por coser cuchillas "
            "de afeitar en las viseras de sus gorras. Una implacable crónica de ambición, política y lealtad familiar."
        )
        await client_prod.send_message(bunker_prod, sinopsis_pb, reply_to=topic_pb)

    # Recolectar episodios
    pb_files = []
    async for m in client_comm.iter_messages(comm_ent, search="Peaky Blinders", limit=160):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if fn.lower().endswith(('.mkv', '.mp4')) and 'peaky blinders' in fn.lower():
                s, e = parse_episode_sort_key(fn)
                if 1 <= s <= 6 and 1 <= e <= 6:
                    pb_files.append((s, e, m.id, fn, m.file.size))

    by_ep_pb = {}
    for s, e, mid, fn, sz in pb_files:
        by_ep_pb.setdefault((s, e), []).append((mid, fn, sz))

    selected_pb = {}
    for s in range(1, 7):
        for e in range(1, 7):
            variants = by_ep_pb.get((s, e), [])
            if variants:
                best = sorted(variants, key=lambda x: (1 if '1080' in x[1] else 0, x[2]), reverse=True)[0]
                selected_pb[(s, e)] = best

    # Comprobar existentes en Búnker
    existing_pb = []
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_pb):
        if m.id != topic_pb and m.file:
            existing_pb.append(m)

    print(f"Peaky Blinders: {len(existing_pb)} archivos en Búnker | {len(selected_pb)} identificados.")
    if len(existing_pb) < len(selected_pb):
        print(f"Reenviando episodios en orden cronológico estricto uno a uno...")
        sorted_keys = sorted(selected_pb.keys())
        for idx, (s, e) in enumerate(sorted_keys, 1):
            mid, fn, sz = selected_pb[(s, e)]
            await client_comm(ForwardMessagesRequest(
                from_peer=comm_ent,
                to_peer=bunker_comm,
                id=[mid],
                top_msg_id=topic_pb,
                drop_author=True
            ))
            print(f"   [{idx:02d}/36] Reenviado S{s:02d}E{e:02d}: {fn}")
            await asyncio.sleep(1.2)
        print("✓ Peaky Blinders completada con éxito.")
    else:
        print("✓ Peaky Blinders ya está completa en el Búnker.")

    # -------------------------------------------------------------------------
    # 2. BLACK MIRROR
    # -------------------------------------------------------------------------
    print("\n" + "="*60)
    print("📦 2. PROCESANDO: BLACK MIRROR")
    print("="*60)
    topic_bm = await get_or_create_topic(client_prod, bunker_prod, "Black Mirror")

    # Sinopsis
    has_sinopsis_bm = False
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_bm, limit=10):
        if m.text and "Black Mirror" in m.text:
            has_sinopsis_bm = True
            break
    if not has_sinopsis_bm:
        sinopsis_bm = (
            "**Black Mirror** (Serie de TV, 2011–)\n\n"
            "• **Temporadas:** 7 (Completa)\n"
            "• **Episodios:** 33\n"
            "• **Calidad:** MKV 1080p Castellano\n"
            "• **Género:** Ciencia ficción, Distopía, Suspense, Sátira\n\n"
            "**Sinopsis:** Antología creada por Charlie Brooker que explora con agudeza y cinismo el lado oscuro "
            "y las consecuencias psicológicas, éticas y sociales de la tecnología en la humanidad. "
            "Cada episodio plantea una historia independiente autoconclusiva ambientada en realidades cercanas o futuros distópicos."
        )
        await client_prod.send_message(bunker_prod, sinopsis_bm, reply_to=topic_bm)

    # Recolectar episodios
    bm_files = []
    async for m in client_comm.iter_messages(comm_ent, search="Black Mirror", limit=200):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if fn.lower().endswith(('.mkv', '.mp4')) and 'black mirror' in fn.lower():
                s, e = parse_episode_sort_key(fn)
                if 1 <= s <= 7 and 1 <= e <= 10:
                    bm_files.append((s, e, m.id, fn, m.file.size))

    by_ep_bm = {}
    for s, e, mid, fn, sz in bm_files:
        by_ep_bm.setdefault((s, e), []).append((mid, fn, sz))

    selected_bm = {}
    expected_bm = {1: 3, 2: 4, 3: 6, 4: 6, 5: 3, 6: 5, 7: 6}
    for s, max_e in expected_bm.items():
        for e in range(1, max_e + 1):
            variants = by_ep_bm.get((s, e), [])
            if variants:
                best = sorted(variants, key=lambda x: (1 if '1080' in x[1] else 0, x[2]), reverse=True)[0]
                selected_bm[(s, e)] = best

    existing_bm = []
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_bm):
        if m.id != topic_bm and m.file:
            existing_bm.append(m)

    print(f"Black Mirror: {len(existing_bm)} archivos en Búnker | {len(selected_bm)} identificados.")
    if len(existing_bm) < len(selected_bm):
        print(f"Reenviando episodios en orden cronológico estricto uno a uno...")
        sorted_keys = sorted(selected_bm.keys())
        for idx, (s, e) in enumerate(sorted_keys, 1):
            mid, fn, sz = selected_bm[(s, e)]
            await client_comm(ForwardMessagesRequest(
                from_peer=comm_ent,
                to_peer=bunker_comm,
                id=[mid],
                top_msg_id=topic_bm,
                drop_author=True
            ))
            print(f"   [{idx:02d}/{len(sorted_keys)}] Reenviado S{s:02d}E{e:02d}: {fn}")
            await asyncio.sleep(1.2)
        print("✓ Black Mirror completada con éxito.")
    else:
        print("✓ Black Mirror ya está completa en el Búnker.")

    # -------------------------------------------------------------------------
    # 3. CHERNOBYL
    # -------------------------------------------------------------------------
    print("\n" + "="*60)
    print("📦 3. PROCESANDO: CHERNOBYL")
    print("="*60)
    topic_ch = await get_or_create_topic(client_prod, bunker_prod, "Chernobyl")

    # Sinopsis
    has_sinopsis_ch = False
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_ch, limit=10):
        if m.text and "Chernobyl" in m.text:
            has_sinopsis_ch = True
            break
    if not has_sinopsis_ch:
        sinopsis_ch = (
            "**Chernobyl** (Miniserie de TV, 2019)\n\n"
            "• **Temporadas:** 1 (Miniserie Completa)\n"
            "• **Episodios:** 5\n"
            "• **Calidad:** MKV 1080p Castellano\n"
            "• **Género:** Drama histórico, Catástrofe, Suspense\n\n"
            "**Sinopsis:** En abril de 1986, la central nuclear de Chernóbil en Ucrania sufrió una de las mayores "
            "catástrofes provocadas por el ser humano de la historia moderna. Esta miniserie narra de forma rigurosa "
            "y asfixiante los sacrificios heroicos para salvar a Europa de un desastre inimaginable, y las consecuencias "
            "sistémicas de la mentira institucional."
        )
        await client_prod.send_message(bunker_prod, sinopsis_ch, reply_to=topic_ch)

    # Recolectar episodios
    ch_files = []
    async for m in client_comm.iter_messages(comm_ent, search="Chernobyl", limit=30):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if fn.lower().endswith(('.mkv', '.mp4')) and 'chernobyl' in fn.lower():
                s, e = parse_episode_sort_key(fn)
                if s == 1 and 1 <= e <= 5:
                    ch_files.append((s, e, m.id, fn, m.file.size))

    by_ep_ch = {}
    for s, e, mid, fn, sz in ch_files:
        by_ep_ch.setdefault((s, e), []).append((mid, fn, sz))

    selected_ch = {}
    for e in range(1, 6):
        variants = by_ep_ch.get((1, e), [])
        if variants:
            best = sorted(variants, key=lambda x: x[2], reverse=True)[0]
            selected_ch[(1, e)] = best

    existing_ch = []
    async for m in client_prod.iter_messages(bunker_prod, reply_to=topic_ch):
        if m.id != topic_ch and m.file:
            existing_ch.append(m)

    print(f"Chernobyl: {len(existing_ch)} archivos en Búnker | {len(selected_ch)} identificados.")
    if len(existing_ch) < len(selected_ch):
        print(f"Reenviando episodios en orden cronológico estricto uno a uno...")
        sorted_keys = sorted(selected_ch.keys())
        for idx, (s, e) in enumerate(sorted_keys, 1):
            mid, fn, sz = selected_ch[(s, e)]
            await client_comm(ForwardMessagesRequest(
                from_peer=comm_ent,
                to_peer=bunker_comm,
                id=[mid],
                top_msg_id=topic_ch,
                drop_author=True
            ))
            print(f"   [{idx:02d}/05] Reenviado S{s:02d}E{e:02d}: {fn}")
            await asyncio.sleep(1.2)
        print("✓ Chernobyl completada con éxito.")
    else:
        print("✓ Chernobyl ya está completa en el Búnker.")

    print("\n🎉 ¡LOTE 2 TRANSFERIDO Y COMPLETADO CON ÉXITO AL BÚNKER!")
    await client_prod.disconnect()
    await client_comm.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
