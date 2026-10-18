import asyncio
import os
import re
import random
from collections import defaultdict
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import (
    CreateForumTopicRequest,
    ForwardMessagesRequest,
    GetForumTopicsRequest
)

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")

PROD_SERIES = -1004331019870
SOURCE_TOPIC_ID = 8414

# Mapeo de reglas de clasificación
# Tupla: (clave_serie, regex_identificador, topic_id_existente_o_None, nombre_tema_a_crear)
SERIES_RULES = [
    ("watching_you", r'(?i)\bwatching\s*you\b', 8207, "Watching You"),
    ("younger", r'(?i)\byounger\b', None, "Younger"),
    ("your_honor", r'(?i)\b(?:your\s*honor|honor)\b', None, "Your Honor"),
    ("young_pope", r'(?i)\b(?:the\s*)?young\s*pope\b', None, "The Young Pope"),
    ("pretty_face", r'(?i)\byour\s*pretty\s*face\b', None, "Your Pretty Face is Going to Hell"),
    ("crime", r'(?i)\ball\s*you\s*need\s*is\s*crime\b', None, "All You Need Is Crime"),
]

def classify_message(file_name, text):
    fn = file_name or ""
    txt = text or ""
    for key, pattern, existing_tid, topic_title in SERIES_RULES:
        if fn and re.search(pattern, fn):
            return key, topic_title, existing_tid
    for key, pattern, existing_tid, topic_title in SERIES_RULES:
        if txt and re.search(pattern, txt):
            return key, topic_title, existing_tid
    return "you", "You", SOURCE_TOPIC_ID

async def safe_sleep(secs: float):
    await asyncio.sleep(secs)

async def create_topic(client, entity, title: str) -> int:
    print(f"📁 [CREAR TEMA] Creando tema: '{title}'...", flush=True)
    while True:
        try:
            res = await client(CreateForumTopicRequest(
                peer=entity,
                title=title,
                random_id=random.randint(1, 2**63 - 1)
            ))
            new_top_id = None
            for u in getattr(res, 'updates', []):
                if hasattr(u, 'message') and hasattr(u.message, 'id'):
                    new_top_id = u.message.id
                    break
                elif hasattr(u, 'id') and isinstance(u.id, int) and u.id > 1:
                    new_top_id = u.id
                    break
            print(f"   ✅ Tema creado: '{title}' [ID: {new_top_id}]", flush=True)
            await safe_sleep(1.0)
            return new_top_id
        except errors.FloodWaitError as e:
            print(f"   ⏳ FloodWait en creación: esperando {e.seconds}s...", flush=True)
            await safe_sleep(e.seconds + 2)
        except Exception as e:
            print(f"   ❌ Error creando tema '{title}': {e}", flush=True)
            return None

async def forward_and_delete_batch(client, entity, msg_ids: list, target_topic_id: int):
    # Enviar en bloques de 10 mensajes
    chunk_size = 10
    total = len(msg_ids)
    sorted_ids = sorted(msg_ids)
    
    for i in range(0, total, chunk_size):
        chunk = sorted_ids[i:i + chunk_size]
        while True:
            try:
                await client(ForwardMessagesRequest(
                    from_peer=entity,
                    to_peer=entity,
                    id=chunk,
                    random_id=[random.randint(1, 2**63 - 1) for _ in chunk],
                    drop_author=True,
                    top_msg_id=target_topic_id
                ))
                await safe_sleep(0.6)
                
                # Borrar del tema origen
                await client.delete_messages(entity, chunk)
                await safe_sleep(0.4)
                
                print(f"   [{min(i + chunk_size, total)}/{total}] Reenviados {len(chunk)} msgs y borrados del origen", flush=True)
                break
            except errors.FloodWaitError as e:
                print(f"   ⏳ FloodWait en reenvío: esperando {e.seconds}s...", flush=True)
                await safe_sleep(e.seconds + 2)
            except Exception as e:
                print(f"   ⚠️ Error en lote {chunk}: {e}", flush=True)
                break

async def main():
    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client:
        prod_entity = await client.get_entity(PROD_SERIES)
        print(f"=== INICIANDO REORGANIZACIÓN DEL TEMA {SOURCE_TOPIC_ID} ===")
        print(f"Canal: {prod_entity.title}")

        # 1. Escanear y clasificar todos los mensajes del tema 8414
        series_msgs = defaultdict(list)
        total_scanned = 0

        async for m in client.iter_messages(prod_entity, reply_to=SOURCE_TOPIC_ID, reverse=True):
            total_scanned += 1
            fn = m.file.name if m.file else ""
            txt = m.text or ""
            key, topic_title, existing_tid = classify_message(fn, txt)
            series_msgs[key].append({
                "id": m.id,
                "file_name": fn,
                "topic_title": topic_title,
                "existing_tid": existing_tid
            })

        print(f"\nTotal mensajes escaneados en tema {SOURCE_TOPIC_ID}: {total_scanned}")
        print("\n=== RESUMEN DE CLASIFICACIÓN ===")
        for key, msgs in series_msgs.items():
            sample = msgs[0]["file_name"] or msgs[0]["topic_title"]
            print(f"- {key} ({msgs[0]['topic_title']}): {len(msgs)} mensajes (ej: {sample})")

        # 2. Procesar cada serie que no sea 'you'
        for key, msgs in series_msgs.items():
            if key == "you":
                print(f"\n👉 'You' se mantiene intacto en Topic {SOURCE_TOPIC_ID} ({len(msgs)} mensajes).")
                continue

            target_title = msgs[0]["topic_title"]
            target_tid = msgs[0]["existing_tid"]

            # Si no tiene tema existente, crearlo
            if not target_tid:
                target_tid = await create_topic(client, prod_entity, target_title)
                if not target_tid:
                    print(f"❌ Saltando {key} por fallo al crear tema.")
                    continue

            msg_ids_to_move = [m["id"] for m in msgs]
            print(f"\n🚀 Moviendo {len(msg_ids_to_move)} mensajes de '{target_title}' hacia Topic {target_tid}...")
            await forward_and_delete_batch(client, prod_entity, msg_ids_to_move, target_tid)
            print(f"✅ Finalizado traslado de '{target_title}'.")

        # 3. Verificación final de mensajes restantes en 8414
        remaining_count = 0
        async for _ in client.iter_messages(prod_entity, reply_to=SOURCE_TOPIC_ID):
            remaining_count += 1

        print(f"\n==================================================")
        print(f"🎉 REORGANIZACIÓN COMPLETADA CON ÉXITO")
        print(f"Mensajes restantes en Tema {SOURCE_TOPIC_ID} (You): {remaining_count}")
        print(f"==================================================")

if __name__ == "__main__":
    asyncio.run(main())
