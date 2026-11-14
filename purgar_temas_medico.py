import os
import sys
import json
import asyncio
import logging
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetForumTopicsRequest, DeleteTopicHistoryRequest

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("PurgarMedicoFamilia")

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD") or ""

SERIES_ESPANOLAS_ID = -1004419790119
COMMUNITY_GROUP_ID = int(os.getenv("COMMUNITY_GROUP_ID", "-1003990716596"))
COMMUNITY_TOPIC_ID = int(os.getenv("COMMUNITY_TOPIC_ID", "22"))

async def main():
    if not SESSION_PROD:
        logger.error("❌ ERROR: SESSION_PROD no configurada.")
        sys.exit(1)

    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client:
        me = await client.get_me()
        logger.info(f"Conectado como: {me.first_name} (ID: {me.id})")

        group = await client.get_input_entity(SERIES_ESPANOLAS_ID)
        logger.info(f"Escaneando temas en Series Españolas ({SERIES_ESPANOLAS_ID})...")

        # 1. Obtener todos los temas del supergrupo
        offset_date = None
        offset_id = 0
        offset_topic = 0
        all_topics = []

        while True:
            try:
                res = await client(GetForumTopicsRequest(
                    peer=group,
                    offset_date=offset_date,
                    offset_id=offset_id,
                    offset_topic=offset_topic,
                    limit=100
                ))
                if not res.topics:
                    break
                all_topics.extend(res.topics)
                if len(res.topics) < 100:
                    break
                offset_topic = res.topics[-1].id
                offset_id = res.topics[-1].top_message
                offset_date = res.topics[-1].date
            except Exception as e:
                logger.error(f"Error obteniendo topics: {e}")
                break

        logger.info(f"Total de temas encontrados: {len(all_topics)}")

        # Filtrar temas a eliminar
        temas_a_eliminar = []
        for t in all_topics:
            title = t.title or ""
            t_lower = title.lower()
            # Identificar temas anómalos: capítulos individuales de Médico de familia o stickers
            if (t_lower.startswith("médico de familia s") or 
                t_lower.startswith("medico de familia s") or 
                t_lower == "sticker"):
                temas_a_eliminar.append((title, t.id))

        logger.info(f"⚠️ Se encontraron {len(temas_a_eliminar)} temas anómalos para eliminar.")

        for title, tid in temas_a_eliminar:
            try:
                logger.info(f"🗑️ Eliminando tema: '{title}' (ID: {tid})...")
                await client(DeleteTopicHistoryRequest(peer=group, top_msg_id=tid))
                await asyncio.sleep(0.5)
            except Exception as de:
                logger.warning(f"Error eliminando topic {tid}: {de}")

        logger.info("✅ Todos los temas anómalos de Médico de familia han sido eliminados del supergrupo.")

        # 2. Limpiar anuncios erróneos en la Comunidad (topic 22)
        try:
            logger.info("Limpiando mensajes erróneos en el topic 22 de Comunidad...")
            comm_ent = await client.get_input_entity(COMMUNITY_GROUP_ID)
            msgs_to_delete = []
            async for m in client.iter_messages(comm_ent, reply_to=COMMUNITY_TOPIC_ID, limit=60):
                txt = m.text or ""
                if "Médico de familia S" in txt or "Medico de familia S" in txt or "sticker" in txt:
                    msgs_to_delete.append(m.id)

            if msgs_to_delete:
                logger.info(f"Borrando {len(msgs_to_delete)} avisos incorrectos en Comunidad...")
                await client.delete_messages(comm_ent, msgs_to_delete)
                logger.info("✅ Avisos eliminados de Comunidad.")
            else:
                logger.info("No se encontraron avisos erróneos pendientes en Comunidad.")
        except Exception as ce:
            logger.warning(f"Aviso limpiando avisos en comunidad: {ce}")

if __name__ == "__main__":
    asyncio.run(main())
