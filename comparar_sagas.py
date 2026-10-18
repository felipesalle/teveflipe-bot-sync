import asyncio
import os
import unicodedata
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetForumTopicsRequest

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")

BUNKER_SAGAS = -1003913363596
PROD_SAGAS = -1004405196455

def normalize(s: str) -> str:
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode('utf-8')
    return s.strip().lower()

async def get_all_topics(client, entity):
    topics = []
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
        if not res.topics:
            break
        topics.extend(res.topics)
        if len(res.topics) < 100:
            break
        last_t = res.topics[-1]
        offset_date = res.messages[-1].date if res.messages else None
        offset_id = res.messages[-1].id if res.messages else 0
        offset_topic = last_t.id
    return topics

async def count_files_in_topic(client, entity, topic_id):
    count = 0
    names = []
    async for m in client.iter_messages(entity, reply_to=topic_id):
        if m.id == topic_id:
            continue
        if m.file:
            count += 1
            if len(names) < 3 and hasattr(m.file, 'name') and m.file.name:
                names.append(m.file.name)
    return count, names

async def main():
    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client:
        bunker = await client.get_entity(BUNKER_SAGAS)
        prod = await client.get_entity(PROD_SAGAS)

        print(f"Búnker: {bunker.title} (ID: {bunker.id})")
        print(f"Producción: {prod.title} (ID: {prod.id})")

        print("\n📡 Obteniendo catálogo de temas en Búnker...")
        bunker_topics = await get_all_topics(client, bunker)
        print(f"Total temas en Búnker: {len(bunker_topics)}")

        print("\n📡 Obteniendo catálogo de temas en Producción...")
        prod_topics = await get_all_topics(client, prod)
        print(f"Total temas en Producción: {len(prod_topics)}")

        prod_topics_map = {normalize(t.title): t for t in prod_topics}

        print("\n" + "="*80)
        print("COMPARACIÓN DETALLADA DE SAGAS & FRANQUICIAS (BÚNKER vs PRODUCCIÓN)")
        print("="*80)

        total_bunker_files = 0
        total_prod_files = 0
        descuadres = []
        coincidentes = 0

        for bt in bunker_topics:
            bt_norm = normalize(bt.title)
            b_count, b_samples = await count_files_in_topic(client, bunker, bt.id)
            total_bunker_files += b_count

            pt = prod_topics_map.get(bt_norm)
            if not pt:
                print(f"❌ FALTA EN PROD: Tema '{bt.title}' ({b_count} archivos en Búnker)")
                descuadres.append((bt.title, b_count, 0, "No existe tema en Producción"))
                continue

            p_count, p_samples = await count_files_in_topic(client, prod, pt.id)
            total_prod_files += p_count

            if b_count == p_count:
                coincidentes += 1
                print(f"✅ OK: '{bt.title}' -> {b_count}/{p_count} archivos")
            else:
                print(f"⚠️ DIFERENCIA: '{bt.title}' -> Búnker: {b_count} | Producción: {p_count}")
                descuadres.append((bt.title, b_count, p_count, f"Diferencia de {abs(b_count - p_count)} archivos"))

        print("\n" + "="*80)
        print("RESUMEN DE AUDITORÍA SAGAS & FRANQUICIAS")
        print("="*80)
        print(f"Temas en Búnker: {len(bunker_topics)}")
        print(f"Temas en Producción: {len(prod_topics)}")
        print(f"Temas con coincidencia exacta (100% idénticos): {coincidentes}")
        print(f"Total archivos en Búnker: {total_bunker_files}")
        print(f"Total archivos en Producción: {total_prod_files}")

        if not descuadres:
            print("\n🎉 ¡EL CANAL DE PRODUCCIÓN ES 100% IDÉNTICO AL BÚNKER!")
        else:
            print(f"\n⚠️ Se encontraron {len(descuadres)} descuadres:")
            for title, bc, pc, motivo in descuadres:
                print(f"   - {title}: Búnker={bc}, Prod={pc} ({motivo})")

if __name__ == "__main__":
    asyncio.run(main())
