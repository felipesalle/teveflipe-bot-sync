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
logger = logging.getLogger("BorrarIncompatibles")

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_BUNKER = os.getenv("SESSION_BUNKER") or ""
SESSION_PROD = os.getenv("SESSION_PROD") or ""

async def run_deletion():
    session_str = SESSION_BUNKER or SESSION_PROD
    if not session_str:
        logger.error("No hay sesiones configuradas.")
        return

    if not os.path.exists("ids_a_borrar.json"):
        logger.error("No se encontró 'ids_a_borrar.json'.")
        return

    with open("ids_a_borrar.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    msg_ids = data.get("msg_ids", [])
    total_ids = len(msg_ids)
    logger.info(f"Total mensajes/archivos a borrar permanentemente: {total_ids}")

    if total_ids == 0:
        logger.info("No hay mensajes para borrar.")
        return

    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        logger.error("Cliente Telethon no autorizado.")
        await client.disconnect()
        return

    # Localizar canal
    target_channel = None
    async for d in client.iter_dialogs(limit=400):
        s_id = str(d.id)
        d_name = d.name or ""
        if '5498750167' in s_id or '5498750167' in str(abs(d.id)) or 'estrenos hd/4k' in d_name.lower():
            target_channel = d.entity
            logger.info(f"Canal localizado: '{d_name}' (ID: {d.id})")
            break

    if not target_channel:
        logger.error("Canal no encontrado.")
        await client.disconnect()
        return

    c_title = getattr(target_channel, 'title', str(target_channel.id))
    logger.info(f"Iniciando borrado permanente en '{c_title}'...")

    deleted_count = 0
    batch_size = 100
    start_time = time.time()

    for i in range(0, total_ids, batch_size):
        chunk = msg_ids[i:i+batch_size]
        try:
            res = await client.delete_messages(target_channel, chunk)
            deleted_count += len(chunk)
            logger.info(f"  🗑️ Borrados {deleted_count}/{total_ids} mensajes ({round(deleted_count*100/total_ids)}%)...")
        except Exception as e:
            logger.error(f"Error borrando bloque {i}-{i+len(chunk)}: {e}")
        await asyncio.sleep(1.2) # Evitar flood limits de Telegram

    elapsed = round(time.time() - start_time, 1)
    logger.info(f"✅ Proceso de borrado finalizado en {elapsed}s. Total eliminados: {deleted_count}/{total_ids}")

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(run_deletion())
