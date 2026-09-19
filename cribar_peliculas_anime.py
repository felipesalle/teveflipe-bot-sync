import asyncio
import json
import logging
import os
import sys
from telethon import TelegramClient, errors
from telethon.sessions import StringSession

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("CribaPeliculasAnime")

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION = os.environ["TELEGRAM_STRING_SESSION"]

CONFIG_FILE = "anime_config.json"
APROBADAS_FILE = "peliculas_anime_aprobadas.json"

DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"

async def main():
    if not os.path.exists(CONFIG_FILE):
        logger.error(f"No se encontró {CONFIG_FILE}")
        return

    if not os.path.exists(APROBADAS_FILE):
        logger.error(f"No se encontró {APROBADAS_FILE}")
        return

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    with open(APROBADAS_FILE, "r", encoding="utf-8") as f:
        aprobadas = json.load(f)

    approved_ids = {p["message_id"] for p in aprobadas}
    logger.info(f"Cargadas {len(approved_ids)} películas anime aprobadas para conservar en el canal.")

    movies_channel_id = config.get("movies_channel_id")
    if not movies_channel_id:
        logger.error("No se encontró movies_channel_id en anime_config.json")
        return

    logger.info(f"Conectando a Telegram (DRY_RUN={DRY_RUN}) en el canal {movies_channel_id}...")

    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        channel = await client.get_entity(movies_channel_id)
        logger.info(f"Canal resuelto con éxito: '{getattr(channel, 'title', movies_channel_id)}'")

        conservar_ids = []
        borrar_ids = []
        total_scanned = 0

        async for msg in client.iter_messages(channel, limit=None):
            total_scanned += 1
            if total_scanned % 1000 == 0:
                logger.info(f"Escaneados {total_scanned} mensajes del canal...")

            # Si el mensaje no tiene media o es mensaje de servicio (ej. 'canal creado')
            # lo dejamos o borramos según sea media
            if not msg.media:
                continue

            if msg.id in approved_ids:
                conservar_ids.append(msg.id)
            else:
                borrar_ids.append(msg.id)

        logger.info("=" * 65)
        logger.info(f"AUDITORÍA COMPLETA DEL CANAL '{channel.title}':")
        logger.info(f"  • Total mensajes escaneados:           {total_scanned}")
        logger.info(f"  🎬 Películas Anime a CONSERVAR:         {len(conservar_ids)}")
        logger.info(f"  🗑️ Series / Capítulos / Basura a BORRAR: {len(borrar_ids)}")
        logger.info("=" * 65)

        if DRY_RUN:
            logger.info("⚠️ MODO DRY_RUN ACTIVO: No se borró ningún mensaje. Para ejecutar la purga definitiva, activa DRY_RUN=false.")
            return

        if not borrar_ids:
            logger.info("✨ El canal ya se encuentra 100% limpio. No hay mensajes que borrar.")
            return

        # Proceder con la eliminación en bloques de 100 mensajes
        logger.info(f"Iniciando purga de {len(borrar_ids)} mensajes en lotes de 100...")
        chunk_size = 100
        borrados_acumulados = 0

        for i in range(0, len(borrar_ids), chunk_size):
            chunk = borrar_ids[i:i + chunk_size]
            success = False
            while not success:
                try:
                    await client.delete_messages(channel, chunk)
                    borrados_acumulados += len(chunk)
                    if (i // chunk_size) % 5 == 0 or borrados_acumulados >= len(borrar_ids):
                        logger.info(f"🗑️ Eliminados {borrados_acumulados} / {len(borrar_ids)} mensajes ({round((borrados_acumulados / len(borrar_ids)) * 100, 1)}%)...")
                    success = True
                    await asyncio.sleep(1.2)
                except errors.FloodWaitError as e:
                    logger.warning(f"FloodWait detectado: esperando {e.seconds + 2}s...")
                    await asyncio.sleep(e.seconds + 2)
                except Exception as ex:
                    logger.error(f"Error eliminando bloque de mensajes: {ex}")
                    success = True  # continuar con el siguiente bloque

        logger.info("🎉 ¡PURGA Y CRIBA COMPLETADA! El canal ahora contiene exclusivamente las películas anime legítimas.")

if __name__ == "__main__":
    asyncio.run(main())
