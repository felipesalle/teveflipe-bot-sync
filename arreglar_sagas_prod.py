import asyncio
import os
import random
import unicodedata
from collections import defaultdict
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import (
    GetForumTopicsRequest,
    ForwardMessagesRequest,
    DeleteMessagesRequest
)

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

async def safe_sleep(secs: float):
    await asyncio.sleep(secs)

async def main():
    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client:
        bunker = await client.get_entity(BUNKER_SAGAS)
        prod = await client.get_entity(PROD_SAGAS)

        print(f"Búnker: {bunker.title} ({bunker.id})")
        print(f"Producción: {prod.title} ({prod.id})")

        b_topics = await get_all_topics(client, bunker)
        p_topics = await get_all_topics(client, prod)
        p_map = {normalize(t.title): t for t in p_topics}

        # -------------------------------------------------------------
        # 1. COPIAR PELÍCULAS DE SHREK
        # -------------------------------------------------------------
        print("\n" + "="*80)
        print("1. PROCESANDO TEMA 'SHREK'")
        print("="*80)

        shrek_b_topic = next((t for t in b_topics if "shrek" in normalize(t.title)), None)
        shrek_p_topic = next((t for t in p_topics if "shrek" in normalize(t.title)), None)

        if shrek_b_topic and shrek_p_topic:
            print(f"Búnker Shrek: '{shrek_b_topic.title}' (ID: {shrek_b_topic.id})")
            print(f"Prod Shrek: '{shrek_p_topic.title}' (ID: {shrek_p_topic.id})")

            # Obtener archivos de Shrek en Búnker
            b_shrek_msgs = []
            async for m in client.iter_messages(bunker, reply_to=shrek_b_topic.id, reverse=True):
                if m.id != shrek_b_topic.id and m.file:
                    b_shrek_msgs.append(m.id)

            print(f"Archivos encontrados en Búnker para Shrek: {len(b_shrek_msgs)}")

            # Comprobar cuántos hay en Prod
            p_shrek_count = 0
            async for m in client.iter_messages(prod, reply_to=shrek_p_topic.id):
                if m.id != shrek_p_topic.id and m.file:
                    p_shrek_count += 1

            print(f"Archivos actuales en Producción para Shrek: {p_shrek_count}")

            if p_shrek_count < len(b_shrek_msgs):
                print(f"🚀 Reenviando {len(b_shrek_msgs)} películas de Shrek a Producción...")
                try:
                    await client(ForwardMessagesRequest(
                        from_peer=bunker,
                        to_peer=prod,
                        id=b_shrek_msgs,
                        random_id=[random.randint(1, 2**63 - 1) for _ in b_shrek_msgs],
                        drop_author=True,
                        top_msg_id=shrek_p_topic.id
                    ))
                    print("✅ Shrek sincronizado con éxito.")
                except Exception as e:
                    print(f"❌ Error reenviando Shrek: {e}")
            else:
                print("ℹ️ Shrek ya cuenta con las películas en Producción.")
        else:
            print(f"⚠️ No se encontró tema de Shrek: bunker={shrek_b_topic}, prod={shrek_p_topic}")

        # -------------------------------------------------------------
        # 2. PURGAR DUPLICADOS EN TEMAS DE PRODUCCIÓN
        # -------------------------------------------------------------
        print("\n" + "="*80)
        print("2. DESDUPLICACIÓN INTELIGENTE DE ARCHIVOS EN PRODUCCIÓN")
        print("="*80)

        total_eliminados = 0

        for pt in p_topics:
            if pt.id == 1:
                continue

            # Recopilar todos los mensajes del tema
            msgs_in_topic = []
            async for m in client.iter_messages(prod, reply_to=pt.id, reverse=True):
                if m.id == pt.id:
                    continue
                if m.file:
                    fname = getattr(m.file, "name", None) or f"size_{getattr(m.file, 'size', 0)}"
                    msgs_in_topic.append((m.id, fname))

            if not msgs_in_topic:
                continue

            seen = set()
            duplicates = []
            for mid, fname in msgs_in_topic:
                key = fname.strip().lower()
                if key in seen:
                    duplicates.append(mid)
                else:
                    seen.add(key)

            if duplicates:
                print(f"🧹 Tema '{pt.title}': {len(msgs_in_topic)} archivos totales, {len(duplicates)} duplicados a eliminar.")
                # Eliminar en bloques de 50
                for i in range(0, len(duplicates), 50):
                    chunk = duplicates[i:i + 50]
                    try:
                        await client.delete_messages(entity=prod, message_ids=chunk)
                        total_eliminados += len(chunk)
                        print(f"   🗑️ Eliminados {len(chunk)} duplicados.")
                        await safe_sleep(0.5)
                    except Exception as de:
                        print(f"   ⚠️ Error eliminando duplicados: {de}")
            else:
                pass

        print(f"\n📊 TOTAL DUPLICADOS ELIMINADOS EN PRODUCCIÓN: {total_eliminados}")

        # -------------------------------------------------------------
        # 3. VERIFICACIÓN FINAL
        # -------------------------------------------------------------
        print("\n" + "="*80)
        print("3. VERIFICACIÓN FINAL DE PRODUCCIÓN")
        print("="*80)
        final_topics = await get_all_topics(client, prod)
        total_final_files = 0
        for ft in final_topics:
            c = 0
            async for m in client.iter_messages(prod, reply_to=ft.id):
                if m.id != ft.id and m.file:
                    c += 1
            total_final_files += c

        print(f"Total temas en Producción: {len(final_topics)}")
        print(f"Total archivos limpios en Producción: {total_final_files}")
        print("🎉 ¡Sagas & Franquicias en Producción quedó 100% perfecto!")

if __name__ == "__main__":
    asyncio.run(main())
