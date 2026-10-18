import asyncio
import os
import re
import random
from collections import defaultdict
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ForwardMessagesRequest

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")

PROD_SERIES = -1004331019870
SOURCE_TOPIC_ID = 8414

EXISTING_TOPICS = [
    ("watching_you", r'(?i)watching[\s_]+you', 8207, "Watching You"),
    ("younger", r'(?i)younger', 9534, "Younger"),
    ("your_honor", r'(?i)(?:your[\s_]+honor|honor)', 9674, "Your Honor"),
    ("young_pope", r'(?i)(?:the[\s_]+)?young[\s_]+pope', 9745, "The Young Pope"),
    ("pretty_face", r'(?i)your[\s_]+pretty[\s_]+face', 9762, "Your Pretty Face is Going to Hell"),
    ("crime", r'(?i)all[\s_]+you[\s_]+need[\s_]+is[\s_]+crime', 9776, "All You Need Is Crime"),
]

def classify_message(file_name, text):
    fn = file_name or ""
    txt = text or ""
    # Comprobar nombre de archivo primero
    for key, pattern, tid, title in EXISTING_TOPICS:
        if fn and re.search(pattern, fn):
            return key, tid, title
    # Luego comprobar texto
    for key, pattern, tid, title in EXISTING_TOPICS:
        if txt and re.search(pattern, txt):
            return key, tid, title
    return "you", SOURCE_TOPIC_ID, "You"

async def safe_sleep(secs: float):
    await asyncio.sleep(secs)

async def forward_and_delete_batch(client, entity, msg_ids: list, target_topic_id: int):
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
                await client.delete_messages(entity, chunk)
                await safe_sleep(0.4)
                print(f"   [{min(i + chunk_size, total)}/{total}] Reenviados {len(chunk)} msgs a topic {target_topic_id} y borrados de {SOURCE_TOPIC_ID}", flush=True)
                break
            except errors.FloodWaitError as e:
                print(f"   ⏳ FloodWait: esperando {e.seconds}s...", flush=True)
                await safe_sleep(e.seconds + 2)
            except Exception as e:
                print(f"   ⚠️ Error en lote {chunk}: {e}", flush=True)
                break

async def main():
    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client:
        prod_entity = await client.get_entity(PROD_SERIES)
        print("=== ESCANEANDO REMANENTES EN TEMA 8414 ===")

        series_msgs = defaultdict(list)
        total_scanned = 0

        async for m in client.iter_messages(prod_entity, reply_to=SOURCE_TOPIC_ID, reverse=True):
            total_scanned += 1
            fn = m.file.name if m.file else ""
            txt = m.text or ""
            key, tid, title = classify_message(fn, txt)
            series_msgs[key].append({
                "id": m.id,
                "file_name": fn,
                "tid": tid,
                "title": title
            })

        print(f"Total mensajes actuales en 8414: {total_scanned}\n")
        print("=== CLASIFICACIÓN DE REMANENTES ===")
        for key, msgs in series_msgs.items():
            print(f"- {key} ({msgs[0]['title']}): {len(msgs)} mensajes (Destino Topic: {msgs[0]['tid']})")

        # Mover los que no sean 'you'
        for key, msgs in series_msgs.items():
            if key == "you":
                continue
            target_tid = msgs[0]["tid"]
            target_title = msgs[0]["title"]
            msg_ids = [m["id"] for m in msgs]
            print(f"\n🚀 Moviendo {len(msg_ids)} mensajes de '{target_title}' hacia Topic {target_tid}...")
            await forward_and_delete_batch(client, prod_entity, msg_ids, target_tid)
            print(f"✅ Completado {target_title}.")

        # Comprobación final
        final_count = 0
        final_samples = []
        async for m in client.iter_messages(prod_entity, reply_to=SOURCE_TOPIC_ID):
            final_count += 1
            if len(final_samples) < 10:
                fn = m.file.name if m.file else (m.text[:30] if m.text else "")
                final_samples.append(fn)

        print(f"\n==================================================")
        print(f"🎉 LIMPIEZA FINALIZADA")
        print(f"Mensajes restantes en Tema 8414 (You): {final_count}")
        print(f"Ejemplos en el tema 8414: {final_samples[:5]}")
        print(f"==================================================")

if __name__ == "__main__":
    asyncio.run(main())
