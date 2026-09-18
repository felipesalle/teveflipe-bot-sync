import asyncio
import json
import logging
import os
import re
from telethon import TelegramClient, utils, errors
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaDocument, DocumentAttributeVideo, DocumentAttributeFilename

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("CribarPeliculas")

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION = os.environ["TELEGRAM_STRING_SESSION"]

CONFIG_FILE = "anime_config.json"
CRIBA_REPORT_FILE = "criba_peliculas_reporte.json"

DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"  # Si es true, solo analiza sin borrar

def get_video_duration(message) -> int:
    if getattr(message, "video", None) and hasattr(message.video, "duration"):
        return message.video.duration or 0
    if message.media and isinstance(message.media, MessageMediaDocument) and message.media.document:
        for attr in message.media.document.attributes:
            if isinstance(attr, DocumentAttributeVideo):
                return getattr(attr, "duration", 0) or 0
    return 0

def extract_file_name(message) -> str:
    if message.media and isinstance(message.media, MessageMediaDocument) and message.media.document:
        for attr in message.media.document.attributes:
            if isinstance(attr, DocumentAttributeFilename):
                return attr.file_name or ""
    return ""

def es_pelicula_real(filename: str, caption: str, duration_sec: int) -> tuple[bool, str]:
    """
    Evalúa si un mensaje es realmente una película o un episodio de serie colado.
    Devuelve (es_pelicula, razon)
    """
    text = (filename + " " + caption).strip().lower()
    dur_min = duration_sec / 60.0

    # Si contiene indicadores evidentes de capítulo / episodio / temporada
    if re.search(r"\b(?:0\d|1\d|2\d)[xX](?:0\d|1\d|2\d)\b", text):
        return False, "Patrón de capítulo (ej. 01X01)"
    if re.search(r"\b(?:s|t)\d{1,2}\s*[-_xX]?\s*(?:e|ep|cap[ií]tulo)?\s*\d{1,3}\b", text):
        return False, "Patrón Temporada/Capítulo (ej. S01E02)"
    if re.search(r"(?i)\b(?:cap[ií]tulo|cap\.|episodio|ep\.)\s*\d+\b", text):
        # Excepción: si es saga o recopilatorio largo, pero sigue siendo serie
        return False, "Contiene palabra 'capítulo/episodio'"
    if re.search(r"\bcap\.\s*\d+_\d+\b", text):
        return False, "Recopilatorio de capítulos (ej. Cap.01_07)"

    # Si dice explícitamente película o movie
    if re.search(r"(?i)\b(pel[ií]cula|movie|film|gekijouban)\b", text):
        return True, "Etiqueta explícita de Película/Movie"

    # Por duración
    if dur_min >= 55.0:
        return True, f"Duración de largometraje ({round(dur_min, 1)} min)"

    # Si dura menos de 40 min y no tiene nada especial, es típicamente un episodio de anime (24 min)
    if 0 < dur_min < 45.0:
        return False, f"Duración estándar de capítulo ({round(dur_min, 1)} min)"

    return False, "Indeterminado o sospechoso de serie"

async def main():
    if not os.path.exists(CONFIG_FILE):
        logger.error(f"No existe {CONFIG_FILE}")
        return

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    movies_id = config.get("movies_channel_id")
    if not movies_id:
        logger.error("No se encontró movies_channel_id en config.")
        return

    logger.info(f"Conectando a Telegram para cribar el canal: {movies_id} (DRY_RUN={DRY_RUN})...")
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        channel = await client.get_entity(movies_id)
        logger.info(f"Canal resuelto: {getattr(channel, 'title', movies_id)}")

        total_scanned = 0
        peliculas_confirmadas = []
        series_coladas = []

        async for msg in client.iter_messages(channel, limit=None):
            if not msg.media:
                continue
            total_scanned += 1
            if total_scanned % 500 == 0:
                logger.info(f"Analizados {total_scanned} mensajes en el canal...")

            fn = extract_file_name(msg)
            caption = msg.text or ""
            dur = get_video_duration(msg)

            es_peli, razon = es_pelicula_real(fn, caption, dur)

            item = {
                "message_id": msg.id,
                "file_name": fn,
                "caption": caption[:100],
                "duration_min": round(dur / 60.0, 1),
                "razon": razon
            }

            if es_peli:
                peliculas_confirmadas.append(item)
            else:
                series_coladas.append(item)

        logger.info("\n" + "=" * 60)
        logger.info(f"RESULTADO DE LA CRIBA (Total Analizados: {total_scanned}):")
        logger.info(f"  🎬 Películas Reales Confirmadas: {len(peliculas_confirmadas)}")
        logger.info(f"  ❌ Series / Capítulos Colados:     {len(series_coladas)}")
        logger.info("=" * 60)

        report = {
            "total_mensajes": total_scanned,
            "total_peliculas": len(peliculas_confirmadas),
            "total_coladas": len(series_coladas),
            "peliculas": peliculas_confirmadas,
            "coladas": series_coladas
        }
        with open(CRIBA_REPORT_FILE, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        # Si DRY_RUN es False, procedemos a borrar los mensajes colados en lotes de 100
        if not DRY_RUN and series_coladas:
            logger.info(f"Iniciando eliminación de {len(series_coladas)} mensajes de series coladas...")
            coladas_ids = [c["message_id"] for c in series_coladas]
            chunk_size = 100
            for i in range(0, len(coladas_ids), chunk_size):
                chunk = coladas_ids[i:i + chunk_size]
                try:
                    await client.delete_messages(channel, chunk)
                    logger.info(f"🗑️ Eliminados {len(chunk)} mensajes ({i + len(chunk)} / {len(coladas_ids)})...")
                    await asyncio.sleep(1.5)
                except errors.FloodWaitError as e:
                    logger.warning(f"FloodWait eliminando: esperando {e.seconds}s...")
                    await asyncio.sleep(e.seconds + 1)
                except Exception as e:
                    logger.error(f"Error eliminando mensajes: {e}")

            logger.info("✨ Limpieza completada. El canal de películas ahora solo contiene películas reales.")

if __name__ == "__main__":
    asyncio.run(main())
