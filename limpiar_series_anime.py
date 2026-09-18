import asyncio
import json
import logging
import os
from telethon import TelegramClient, utils, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetForumTopicsRequest, DeleteTopicHistoryRequest

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("LimpiarSeries")

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION = os.environ["TELEGRAM_STRING_SESSION"]

CONFIG_FILE = "anime_config.json"
STATE_FILE = "sync_state_anime.json"

async def main():
    if not os.path.exists(CONFIG_FILE):
        logger.error(f"No existe {CONFIG_FILE}")
        return

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    series_id = config.get("series_group_id")
    if not series_id:
        logger.error("No se encontró series_group_id en config.")
        return

    logger.info(f"Conectando a Telegram para limpiar temas en {series_id}...")
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        group = await client.get_entity(series_id)
        logger.info(f"Grupo resuelto: {getattr(group, 'title', series_id)}")

        # Obtener todos los temas existentes
        res = await client(GetForumTopicsRequest(
            peer=group,
            offset_date=None,
            offset_id=0,
            offset_topic=0,
            limit=100
        ))

        topics = getattr(res, "topics", [])
        logger.info(f"Total temas encontrados en el grupo: {len(topics)}")

        for t in topics:
            if t.id == 1:
                continue
            logger.info(f"🗑️ Eliminando tema: '{t.title}' (ID {t.id})...")
            try:
                await client(DeleteTopicHistoryRequest(peer=group, top_msg_id=t.id))
                logger.info(f"  -> Eliminado con éxito: '{t.title}'")
                await asyncio.sleep(1.0)
            except errors.FloodWaitError as e:
                logger.warning(f"FloodWait eliminando tema: esperando {e.seconds}s...")
                await asyncio.sleep(e.seconds + 1)
            except Exception as e:
                logger.warning(f"Aviso eliminando tema {t.id}: {e}")

        logger.info("✨ Limpieza de temas de series finalizada. El grupo está limpio.")

    # Resetear el archivo de estado para series
    st = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                st = json.load(f)
        except Exception:
            pass
    st["completed_series"] = []
    st["series_topics"] = {}
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2, ensure_ascii=False)
    logger.info("Estado de sincronización de series inicializado/reseteado.")

if __name__ == "__main__":
    asyncio.run(main())
