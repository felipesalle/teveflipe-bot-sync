import os
import json
import asyncio
import re
import logging
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.functions.channels import CreateChannelRequest
from telethon.tl.functions.messages import ExportChatInviteRequest
from telethon.tl.types import (
    MessageMediaDocument,
    DocumentAttributeVideo,
    DocumentAttributeFilename,
    PeerChannel
)

logging.basicConfig(
    format="[%(asctime)s] %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("SyncInfantil")

# 1. CREDENCIALES DE TELEGRAM
API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION", "")

# 2. CANAL ORIGEN Y TEMA (Chat: -1002257262928, Topic: 316308)
SOURCE_CHAT_ID = int(os.getenv("INFANTIL_SOURCE_CHAT", "-1002257262928"))
SOURCE_TOPIC_ID = int(os.getenv("INFANTIL_SOURCE_TOPIC", "316308"))

CHECKPOINT_FILE = "checkpoint_infantil.json"
BATCH_SIZE = 50  # Lote masivo de reenvío por bloques
VIDEO_EXTENSIONS = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.m4v', '.webm', '.ts')


def es_archivo_video(msg) -> bool:
    """Filtra y descarta imágenes sueltas, archivos de texto, subtítulos o promociones."""
    if not msg or not msg.media:
        return False
    if getattr(msg, "video", None):
        return True
    if getattr(msg, "file", None):
        mime = (getattr(msg.file, 'mime_type', '') or '').lower()
        if mime.startswith('video/'):
            return True
        name = (getattr(msg.file, 'name', '') or '').lower()
        if name.endswith(VIDEO_EXTENSIONS):
            return True
    if isinstance(msg.media, MessageMediaDocument) and msg.media.document:
        doc = msg.media.document
        mime = (doc.mime_type or '').lower()
        if mime.startswith('video/'):
            return True
        for attr in doc.attributes:
            if isinstance(attr, DocumentAttributeVideo):
                return True
            if isinstance(attr, DocumentAttributeFilename):
                fname = (attr.file_name or '').lower()
                if fname.endswith(VIDEO_EXTENSIONS):
                    return True
    return False


def get_video_info(msg) -> tuple:
    """Extrae texto descriptivo, duración en segundos y nombre de archivo."""
    texto = (msg.raw_text or "") + " "
    name = ""
    duracion = 0
    if getattr(msg, "file", None):
        name = getattr(msg.file, "name", "") or ""
        duracion = getattr(msg.file, "duration", 0) or 0

    if not duracion and isinstance(msg.media, MessageMediaDocument) and msg.media.document:
        for attr in msg.media.document.attributes:
            if hasattr(attr, "duration") and attr.duration:
                duracion = attr.duration
            if isinstance(attr, DocumentAttributeFilename) and not name:
                name = attr.file_name or ""

    texto += name
    return texto, duracion, name


def clasificar_archivo(msg) -> str:
    """
    Clasificación híbrida (Duración + Regex):
    - Menos de 45 minutos (2700s) o con patrones de capítulo -> 'SERIE'
    - Más de 50 minutos (3000s) -> 'PELICULA'
    - Fallback: Palabras clave 'pelicula', 'movie', 'film' -> 'PELICULA'
    - Por defecto en contenido infantil de animación -> 'SERIE'
    """
    texto, duracion, name = get_video_info(msg)

    # 1. Por patrones claros de nombres de series/episodios
    if re.search(r'(?i)(?:s\d{1,2}|temporada|temp\b|episodio|cap[íi]tulo|cap[.\s\d]|parte|\bep\b|\d{1,2}x\d{1,2}|\b[-–—_]\s*\d{1,3}\b|\b\d{1,3}\s*[-–—_])', texto):
        return "SERIE"

    # 2. Por duración
    if duracion > 0:
        if duracion < 2700:      # Menos de 45 minutos -> Serie
            return "SERIE"
        elif duracion >= 3000:   # 50 minutos o más -> Película
            return "PELICULA"

    # 3. Fallback de palabras clave si no hay duración clara (o entre 45 y 50 min)
    # Nota: No incluir 'dvdrip' o '1080p' para no clasificar series como películas
    if re.search(r'(?i)\b(?:pelicula|pel[ií]cula|movie|film|largometraje)\b', texto):
        return "PELICULA"

    # Si tiene numeración en el nombre del archivo (ej. Fraggle_Rock_01.avi)
    if re.search(r'\b\d{1,3}\b', name):
        return "SERIE"

    return "SERIE"


def cargar_progreso() -> dict:
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Error leyendo {CHECKPOINT_FILE}: {e}")
    return {
        "last_msg_id": 0,
        "canal_pelis_id": None,
        "canal_series_id": None,
        "canal_pelis_link": None,
        "canal_series_link": None,
        "pelis_count": 0,
        "series_count": 0,
        "descartados": 0
    }


def guardar_progreso(data: dict):
    try:
        with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error guardando {CHECKPOINT_FILE}: {e}")


async def forward_batch(client: TelegramClient, source_entity, dest_entity, msg_ids: list, tipo=""):
    """Transfiere los mensajes en un solo bloque rápido usando forward_messages sin autor."""
    if not msg_ids:
        return

    enviado = False
    intentos = 0
    while not enviado and intentos < 5:
        intentos += 1
        try:
            await client.forward_messages(
                dest_entity,
                msg_ids,
                from_peer=source_entity,
                drop_author=True
            )
            logger.info(f"🚀 Lote masivo enviado: {len(msg_ids)} {tipo} transferidos con éxito.")
            await asyncio.sleep(3.5)
            enviado = True
        except errors.FloodWaitError as e:
            logger.warning(f"⚠️ Telegram FloodWait: pausando {e.seconds}s de seguridad...")
            await asyncio.sleep(e.seconds + 2)
        except Exception as e:
            logger.warning(f"⚠️ Error enviando lote a {tipo} ({e}). Reintentando individualmente...")
            for mid in msg_ids:
                try:
                    await client.forward_messages(
                        dest_entity,
                        mid,
                        from_peer=source_entity,
                        drop_author=True
                    )
                    await asyncio.sleep(0.6)
                except Exception as ex_single:
                    logger.debug(f"Saltando mensaje {mid}: {ex_single}")
            enviado = True


async def resolve_channel_entity(client: TelegramClient, channel_id, invite_link=None):
    """Resuelve la entidad del canal de forma robusta."""
    if invite_link:
        try:
            return await client.get_entity(invite_link)
        except Exception as e:
            logger.warning(f"No se pudo resolver canal por enlace {invite_link}: {e}")
    try:
        clean_id = abs(int(channel_id))
        if str(clean_id).startswith("100") and len(str(clean_id)) > 10:
            clean_id = int(str(clean_id)[3:])
        return await client.get_entity(PeerChannel(clean_id))
    except Exception as e:
        logger.warning(f"Error resolviendo PeerChannel({channel_id}): {e}")
        return await client.get_entity(channel_id)


async def main():
    if not STRING_SESSION:
        logger.error("❌ ERROR: TELEGRAM_STRING_SESSION no configurada.")
        return

    logger.info("Iniciando conexión con Telegram...")
    async with TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH) as client:
        me = await client.get_me()
        logger.info(f"Conectado como: {me.first_name} (@{me.username or 'sin_username'})")

        source_entity = await client.get_entity(SOURCE_CHAT_ID)
        source_title = getattr(source_entity, "title", str(SOURCE_CHAT_ID))
        logger.info(f"📦 Canal Origen: {source_title} (ID: {SOURCE_CHAT_ID}, Topic: {SOURCE_TOPIC_ID})")

        progreso = cargar_progreso()

        # 1. GESTIÓN CANAL DE PELÍCULAS INFANTILES
        if not progreso.get("canal_pelis_id"):
            logger.info("Creando canal privado: 'Películas Infantiles'...")
            res_p = await client(CreateChannelRequest(
                title="Películas Infantiles",
                about="Canal oficial de Películas Infantiles para TeveFlipe",
                megagroup=False
            ))
            ent_pelis = res_p.chats[0]
            inv_p = await client(ExportChatInviteRequest(peer=ent_pelis))
            p_id = int(f"-100{ent_pelis.id}") if str(ent_pelis.id)[0] != '-' else ent_pelis.id
            progreso["canal_pelis_id"] = p_id
            progreso["canal_pelis_link"] = inv_p.link
            logger.info(f"✅ Creado Películas Infantiles: ID={p_id} | Enlace: {inv_p.link}")
            guardar_progreso(progreso)
        else:
            ent_pelis = await resolve_channel_entity(client, progreso["canal_pelis_id"], progreso.get("canal_pelis_link"))

        # 2. GESTIÓN CANAL DE SERIES INFANTILES (Canal normal broadcast)
        if not progreso.get("canal_series_id"):
            logger.info("Creando canal privado: 'Series Infantiles'...")
            res_s = await client(CreateChannelRequest(
                title="Series Infantiles",
                about="Canal oficial de Series Infantiles y Animación para TeveFlipe",
                megagroup=False
            ))
            ent_series = res_s.chats[0]
            inv_s = await client(ExportChatInviteRequest(peer=ent_series))
            s_id = int(f"-100{ent_series.id}") if str(ent_series.id)[0] != '-' else ent_series.id
            progreso["canal_series_id"] = s_id
            progreso["canal_series_link"] = inv_s.link
            logger.info(f"✅ Creado Series Infantiles: ID={s_id} | Enlace: {inv_s.link}")
            guardar_progreso(progreso)
        else:
            ent_series = await resolve_channel_entity(client, progreso["canal_series_id"], progreso.get("canal_series_link"))

        print("\n" + "═" * 70)
        print("CANALES DESTINO PARA EL PANEL WEB (admin.html):")
        print(f"🎬 Películas Infantiles: ID={progreso['canal_pelis_id']} | Link={progreso['canal_pelis_link']}")
        print(f"📺 Series Infantiles:    ID={progreso['canal_series_id']} | Link={progreso['canal_series_link']}")
        print("═" * 70 + "\n")

        ultimo_id = progreso.get("last_msg_id", 0)
        total_pelis = progreso.get("pelis_count", 0)
        total_series = progreso.get("series_count", 0)
        total_descartados = progreso.get("descartados", 0)

        logger.info(f"Iniciando sincronización desde mensaje ID: {ultimo_id}")
        logger.info(f"Estado inicial: {total_pelis} pelis | {total_series} series | {total_descartados} descartados")

        lote_pelis = []
        lote_series = []

        total_scanned = 0
        async for msg in client.iter_messages(
            source_entity,
            reply_to=SOURCE_TOPIC_ID,
            min_id=ultimo_id,
            reverse=True
        ):
            ultimo_id = msg.id
            total_scanned += 1

            # 1. Filtro de archivos basura
            if not es_archivo_video(msg):
                total_descartados += 1
                if total_descartados % 500 == 0:
                    logger.info(f"🧹 Descartados {total_descartados} archivos no-vídeo...")
                    progreso.update({
                        "last_msg_id": ultimo_id,
                        "pelis_count": total_pelis,
                        "series_count": total_series,
                        "descartados": total_descartados
                    })
                    guardar_progreso(progreso)
                continue

            # 2. Clasificación híbrida
            tipo = clasificar_archivo(msg)

            if tipo == "PELICULA":
                lote_pelis.append(msg.id)
                total_pelis += 1
                if len(lote_pelis) >= BATCH_SIZE:
                    await forward_batch(client, source_entity, ent_pelis, lote_pelis, tipo="Películas")
                    lote_pelis.clear()
                    progreso.update({
                        "last_msg_id": ultimo_id,
                        "pelis_count": total_pelis,
                        "series_count": total_series,
                        "descartados": total_descartados
                    })
                    guardar_progreso(progreso)
            else:
                lote_series.append(msg.id)
                total_series += 1
                if len(lote_series) >= BATCH_SIZE:
                    await forward_batch(client, source_entity, ent_series, lote_series, tipo="Episodios de Series")
                    lote_series.clear()
                    progreso.update({
                        "last_msg_id": ultimo_id,
                        "pelis_count": total_pelis,
                        "series_count": total_series,
                        "descartados": total_descartados
                    })
                    guardar_progreso(progreso)

            # Notificación de avance periódico
            if (total_pelis + total_series) % 200 == 0:
                logger.info(f"📊 Progreso acumulado: {total_pelis} Películas | {total_series} Series | {total_descartados} Descartados (Último ID: {ultimo_id})")

        # Reenviar remanentes pendientes
        if lote_pelis:
            await forward_batch(client, source_entity, ent_pelis, lote_pelis, tipo="Películas")
            lote_pelis.clear()

        if lote_series:
            await forward_batch(client, source_entity, ent_series, lote_series, tipo="Episodios de Series")
            lote_series.clear()

        progreso.update({
            "last_msg_id": ultimo_id,
            "pelis_count": total_pelis,
            "series_count": total_series,
            "descartados": total_descartados
        })
        guardar_progreso(progreso)

        logger.info("\n🎉 ¡PROCESO DE CLONACIÓN Y CLASIFICACIÓN FINALIZADO!")
        logger.info(f"Total Películas transferidas: {total_pelis}")
        logger.info(f"Total Episodios transferidos: {total_series}")
        logger.info(f"Total Archivos descartados:   {total_descartados}")


if __name__ == "__main__":
    asyncio.run(main())
