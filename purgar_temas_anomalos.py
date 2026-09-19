import asyncio
import json
import logging
import os
import sys
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import DeleteTopicHistoryRequest

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("PurgarTemasAnomalos")

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION = os.environ["TELEGRAM_STRING_SESSION"]

CONFIG_FILE = "anime_config.json"
STATE_FILE = "sync_state_anime.json"
TEMAS_FILE = "temas_a_purgar.json"

async def main():
    if not os.path.exists(CONFIG_FILE):
        logger.error(f"No existe {CONFIG_FILE}")
        return

    if not os.path.exists(TEMAS_FILE):
        logger.error(f"No existe {TEMAS_FILE}")
        return

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    with open(TEMAS_FILE, "r", encoding="utf-8") as f:
        temas_a_purgar = json.load(f)

    series_group_id = config.get("series_group_id")
    if not series_group_id:
        logger.error("No se encontró series_group_id en config.")
        return

    logger.info(f"Conectando a Telegram para purgar {len(temas_a_purgar)} temas anómalos en {series_group_id}...")

    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        group = await client.get_entity(series_group_id)
        logger.info(f"Grupo resuelto: {getattr(group, 'title', series_group_id)}")

        eliminados = 0
        for title, tid in temas_a_purgar.items():
            if tid <= 1:
                continue
            logger.info(f"🗑️ Eliminando tema anómalo: '{title}' (ID {tid})...")
            success = False
            while not success:
                try:
                    await client(DeleteTopicHistoryRequest(peer=group, top_msg_id=tid))
                    eliminados += 1
                    logger.info(f"  ✓ Eliminado con éxito ({eliminados}/{len(temas_a_purgar)})")
                    success = True
                    await asyncio.sleep(1.0)
                except errors.FloodWaitError as e:
                    logger.warning(f"FloodWait: esperando {e.seconds + 2}s...")
                    await asyncio.sleep(e.seconds + 2)
                except Exception as ex:
                    logger.warning(f"Aviso eliminando tema ID {tid} ({title}): {ex}")
                    success = True

        logger.info(f"✨ Purga de temas anómalos finalizada. Total eliminados: {eliminados}")

    # Limpiar sync_state_anime.json
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            st = json.load(f)

        topics_map = st.get("series_topics", {})
        comp_set = set(st.get("completed_series", []))

        for t in temas_a_purgar.keys():
            topics_map.pop(t, None)
            comp_set.discard(t)
            # También en title case
            comp_set.discard(t.title())

        st["series_topics"] = topics_map
        st["completed_series"] = list(comp_set)

        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(st, f, indent=2, ensure_ascii=False)
        logger.info("Estado sync_state_anime.json saneado correctamente.")

if __name__ == "__main__":
    asyncio.run(main())
