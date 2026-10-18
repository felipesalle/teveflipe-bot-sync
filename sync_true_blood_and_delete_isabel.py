import asyncio
import os
import random
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ForwardMessagesRequest

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")

BUNKER_SERIES = -1002097175258
PROD_SERIES = -1004331019870
BUNKER_TOPIC_TRUE_BLOOD = 26137
PROD_TOPIC_TRUE_BLOOD = 9464

async def safe_sleep(secs: float):
    await asyncio.sleep(secs)

async def main():
    if not SESSION_PROD:
        print("❌ ERROR: SESSION_PROD no configurada.")
        return

    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client:
        bunker = await client.get_entity(BUNKER_SERIES)
        prod = await client.get_entity(PROD_SERIES)

        print(f"Origen (Búnker): {bunker.title} ({bunker.id})")
        print(f"Destino (Producción): {prod.title} ({prod.id})")

        # 1. Recopilar capítulos de True Blood desde el Búnker en orden cronológico
        print(f"\n📥 Leyendo capítulos de 'True Blood' desde Búnker (Topic {BUNKER_TOPIC_TRUE_BLOOD})...")
        bunker_msg_ids = []
        async for m in client.iter_messages(bunker, reply_to=BUNKER_TOPIC_TRUE_BLOOD, reverse=True):
            if m.id == BUNKER_TOPIC_TRUE_BLOOD:
                continue
            if m.file:
                bunker_msg_ids.append(m.id)

        print(f"Total capítulos encontrados en Búnker: {len(bunker_msg_ids)}")

        if not bunker_msg_ids:
            print("❌ No se encontraron mensajes con archivos en el tema de Búnker.")
            return

        # 2. Reenviar ordenadamente a Producción Topic 9464
        print(f"\n🚀 Reenviando {len(bunker_msg_ids)} capítulos a Producción (Topic {PROD_TOPIC_TRUE_BLOOD})...")
        chunk_size = 10
        total = len(bunker_msg_ids)
        total_reenviados = 0

        for i in range(0, total, chunk_size):
            chunk = bunker_msg_ids[i:i + chunk_size]
            while True:
                try:
                    await client(ForwardMessagesRequest(
                        from_peer=bunker,
                        to_peer=prod,
                        id=chunk,
                        random_id=[random.randint(1, 2**63 - 1) for _ in chunk],
                        drop_author=True,
                        top_msg_id=PROD_TOPIC_TRUE_BLOOD
                    ))
                    total_reenviados += len(chunk)
                    print(f"   [{total_reenviados}/{total}] Reenviados {len(chunk)} capítulos con éxito.", flush=True)
                    await safe_sleep(1.0)
                    break
                except errors.FloodWaitError as e:
                    print(f"   ⏳ FloodWait: esperando {e.seconds}s...", flush=True)
                    await safe_sleep(e.seconds + 2)
                except Exception as e:
                    print(f"   ❌ Error reenviando bloque {chunk}: {e}", flush=True)
                    break

        # 3. Verificación final en Producción
        print(f"\n🔍 Verificando mensajes en Producción (Topic {PROD_TOPIC_TRUE_BLOOD})...")
        count_prod = 0
        samples = []
        async for m in client.iter_messages(prod, reply_to=PROD_TOPIC_TRUE_BLOOD):
            count_prod += 1
            if len(samples) < 5 and m.file and hasattr(m.file, 'name') and m.file.name:
                samples.append(m.file.name)

        print(f"Total mensajes en Producción Topic {PROD_TOPIC_TRUE_BLOOD}: {count_prod}")
        print(f"Muestra de episodios recibidos: {samples}")
        print("\n🎉 ¡OPERACIÓN COMPLETADA EXITOSAMENTE!")

if __name__ == "__main__":
    asyncio.run(main())
