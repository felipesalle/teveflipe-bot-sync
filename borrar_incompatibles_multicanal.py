import os
import sys
import json
import asyncio
import logging
import time
from telethon import TelegramClient
from telethon.sessions import StringSession

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s")
logger = logging.getLogger("BorrarMultiCanal")

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_BUNKER = os.getenv("SESSION_BUNKER") or ""
SESSION_PROD = os.getenv("SESSION_PROD") or ""

CHANNELS = {
    "pelis_2000": {"id": -1004420612937, "name": "Películas 2000-2019 HD/4K Bunker"},
    "pelis_clasicas": {"id": -1004450378925, "name": "Películas Clásicas HD/4K Bunker"},
    "series": {"id": -1004457839581, "name": "Series HD/4K Bunker"}
}

async def main():
    session_str = SESSION_BUNKER or SESSION_PROD
    if not session_str:
        logger.error("No hay sesiones.")
        return

    if not os.path.exists("ids_a_borrar_multicanal.json"):
        logger.error("No se encontró 'ids_a_borrar_multicanal.json'.")
        return

    with open("ids_a_borrar_multicanal.json", "r", encoding="utf-8") as f:
        del_dict = json.load(f)

    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        logger.error("No autorizado.")
        await client.disconnect()
        return

    chosen_target = os.getenv("CHOSEN_TARGET", "all").lower()
    targets = CHANNELS if chosen_target == "all" else {chosen_target: CHANNELS[chosen_target]}

    for k, info in targets.items():
        ch_id = info["id"]
        ch_name = info["name"]
        ids_to_delete = del_dict.get(k, [])

        if not ids_to_delete:
            logger.info(f"[{ch_name}] No hay mensajes a borrar.")
            continue

        logger.info(f"\n🗑️ Iniciando borrado en '{ch_name}' (Total IDs: {len(ids_to_delete)})...")
        try:
            entity = await client.get_entity(ch_id)
        except Exception as e:
            logger.error(f"Error resolviendo entity {ch_id}: {e}")
            continue

        deleted = 0
        batch_size = 100
        start = time.time()
        for i in range(0, len(ids_to_delete), batch_size):
            chunk = ids_to_delete[i:i+batch_size]
            try:
                await client.delete_messages(entity, chunk)
                deleted += len(chunk)
                logger.info(f"  [{ch_name}] Borrados {deleted}/{len(ids_to_delete)} ({round(deleted*100/len(ids_to_delete))}%)...")
            except Exception as e:
                logger.error(f"Error borrando lote: {e}")
            await asyncio.sleep(1.2)

        elapsed = round(time.time() - start, 1)
        logger.info(f"✅ Finalizado borrado en '{ch_name}' en {elapsed}s. Eliminados: {deleted}/{len(ids_to_delete)}")

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
