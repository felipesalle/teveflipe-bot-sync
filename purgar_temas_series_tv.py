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
logger = logging.getLogger("PurgarSeriesTV")

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION = os.environ["TELEGRAM_STRING_SESSION"]

TARGET_CHAT = int(os.environ.get("SERIES_DEST_CHAT", "-1002097175258"))
TEMAS_FILE = "temas_a_purgar_series_tv.json"
STATE_FILE = "sync_state.json"

async def main():
    if not os.path.exists(TEMAS_FILE):
        logger.error(f"No existe {TEMAS_FILE}")
        return

    with open(TEMAS_FILE, "r", encoding="utf-8") as f:
        temas_a_purgar = json.load(f)

    logger.info(f"Conectando a Telegram para purgar {len(temas_a_purgar)} temas anómalos en chat {TARGET_CHAT}...")

    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        group = await client.get_entity(TARGET_CHAT)
        logger.info(f"Supergrupo resuelto: {getattr(group, 'title', TARGET_CHAT)}")

        eliminados = 0
        total = len(temas_a_purgar)
        for title, tid in temas_a_purgar.items():
            if tid <= 1:
                continue
            logger.info(f"🗑️ Eliminando tema anómalo: '{title}' (ID {tid})...")
            success = False
            while not success:
                try:
                    await client(DeleteTopicHistoryRequest(peer=group, top_msg_id=tid))
                    eliminados += 1
                    logger.info(f"  ✓ Eliminado con éxito ({eliminados}/{total})")
                    success = True
                    await asyncio.sleep(0.8)
                except errors.FloodWaitError as e:
                    logger.warning(f"FloodWait: esperando {e.seconds + 2}s...")
                    await asyncio.sleep(e.seconds + 2)
                except Exception as ex:
                    logger.warning(f"Aviso eliminando tema ID {tid} ({title}): {ex}")
                    success = True

        logger.info(f"✨ Purga completada. Total temas eliminados de Telegram: {eliminados}")

    # Saneamiento de sync_state.json
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            st = json.load(f)

        purged_ids = set(temas_a_purgar.values())
        cache = st.get("series_topics_cache", {})
        cleaned_cache = {k: v for k, v in cache.items() if v not in purged_ids}
        st["series_topics_cache"] = cleaned_cache

        # Resetear estado de serie activa
        st["current_series_title"] = ""
        st["current_topic_id"] = None

        # Resetear series_last_id a 175069 (antes de que comenzara el lote anómalo)
        st["series_last_id"] = 175069

        # Limpiar IDs de mensajes reenviados posteriores a 175069
        fwds = st.get("forwarded_message_ids", [])
        st["forwarded_message_ids"] = [mid for mid in fwds if mid <= 175069]

        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(st, f, indent=2, ensure_ascii=False)
        logger.info(f"💾 {STATE_FILE} saneado correctamente (series_last_id reseteado a 175069).")

if __name__ == "__main__":
    asyncio.run(main())
