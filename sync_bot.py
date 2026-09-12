import os
import re
import json
import asyncio
import logging
from typing import Optional, Dict, List
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import (
    MessageMediaDocument,
    MessageMediaPhoto,
    DocumentAttributeVideo,
    DocumentAttributeFilename,
    Channel
)
import random
from telethon.tl.functions.messages import (
    GetForumTopicsRequest,
    CreateForumTopicRequest
)

# Configuración de Logging
logging.basicConfig(
    format="[%(asctime)s] %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("TeveFlipeSync")

# Credenciales de Telegram (Variables de entorno o por defecto)
API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION", "")

# IDs de Canales y Grupos
MOVIES_SOURCE_CHAT = int(os.getenv("MOVIES_SOURCE_CHAT", "-1001905652210"))
MOVIES_SOURCE_TOPIC = int(os.getenv("MOVIES_SOURCE_TOPIC", "1605935"))
MOVIES_DEST_CHAT = int(os.getenv("MOVIES_DEST_CHAT", "-1002146236969"))

SERIES_SOURCE_CHAT = int(os.getenv("SERIES_SOURCE_CHAT", "-1002257262928"))
SERIES_SOURCE_TOPIC = int(os.getenv("SERIES_SOURCE_TOPIC", "157592"))
SERIES_DEST_CHAT = int(os.getenv("SERIES_DEST_CHAT", "-1002097175258"))

STATE_FILE = "sync_state.json"

# Extensiones de video admitidas
VIDEO_EXTENSIONS = (".mkv", ".mp4", ".avi", ".mov", ".webm", ".ts", ".m4v")


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"No se pudo leer {STATE_FILE}, iniciando estado limpio: {e}")
    return {
        "movies_last_id": 0,
        "series_last_id": 0,
        "series_topics_cache": {},  # { "nombre_serie": topic_id }
        "forwarded_message_ids": []
    }


def save_state(state: dict):
    try:
        # Mantener solo los últimos 5000 IDs para evitar crecimiento desmedido
        if len(state.get("forwarded_message_ids", [])) > 5000:
            state["forwarded_message_ids"] = state["forwarded_message_ids"][-5000:]
            
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        logger.info(f"Estado actualizado y guardado en {STATE_FILE}")
    except Exception as e:
        logger.error(f"Error guardando {STATE_FILE}: {e}")


def is_video_message(message) -> bool:
    """Detecta si un mensaje contiene un archivo multimedia de video."""
    if not message.media:
        return False
    if getattr(message, "video", None):
        return True
    if isinstance(message.media, MessageMediaDocument):
        doc = message.media.document
        if doc:
            if doc.mime_type and doc.mime_type.startswith("video/"):
                return True
            for attr in doc.attributes:
                if isinstance(attr, (DocumentAttributeVideo,)):
                    return True
                if isinstance(attr, DocumentAttributeFilename):
                    if attr.file_name and attr.file_name.lower().endswith(VIDEO_EXTENSIONS):
                        return True
    return False


def extract_file_name(message) -> str:
    """Extrae el nombre del archivo de un mensaje multimedia."""
    if message.media and isinstance(message.media, MessageMediaDocument) and message.media.document:
        for attr in message.media.document.attributes:
            if isinstance(attr, DocumentAttributeFilename):
                return attr.file_name or ""
    return ""


def clean_series_title(raw_title: str) -> str:
    """Limpia el título para extraer únicamente el nombre base de la serie."""
    # Quitar extensión (.mkv, .mp4, etc.)
    text = re.sub(r"\.[a-zA-Z0-9]{2,4}$", "", raw_title)
    # Eliminar enlaces, menciones (@canal) y corchetes de calidad [1080p], [Dual], etc.
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"\[.*?\]|\(.*?\)", "", text)
    
    # Cortar en patrones de temporada/episodio comunes
    parts = re.split(r"(?i)\b(?:S\d+(?:E\d+)?|T\d+(?:E\d+)?|Temporada\s*\d+|\d+x\d+|Cap[ií]tulo\s*\d+|Episodio\s*\d+)\b", text)
    candidates = [p.replace(".", " ").replace("_", " ").strip() for p in parts if p.strip()]
    title = candidates[0] if candidates else text
    title = re.sub(r"^[-–—:\s]+|[-–—:\s]+$", "", title).strip()
    return title.title()


async def sync_movies(client: TelegramClient, state: dict):
    """Sincroniza películas desde el grupo/tema origen hacia el canal destino."""
    logger.info("--- INICIANDO SINCRONIZACIÓN DE PELÍCULAS ---")
    dest_chat = await client.get_input_entity(MOVIES_DEST_CHAT)
    source_chat = await client.get_input_entity(MOVIES_SOURCE_CHAT)
    
    last_id = state.get("movies_last_id", 0)
    logger.info(f"Escaneando películas nuevas posteriores al ID {last_id}...")
    
    # Obtenemos los mensajes recientes del tema (máx 50 por lote en cada ejecución)
    new_movies = []
    async for message in client.iter_messages(
        source_chat,
        reply_to=MOVIES_SOURCE_TOPIC if MOVIES_SOURCE_TOPIC else None,
        min_id=last_id,
        limit=50,
        reverse=True
    ):
        if is_video_message(message):
            if message.id not in state.get("forwarded_message_ids", []):
                new_movies.append(message)

    if not new_movies:
        logger.info("No se encontraron nuevas películas para sincronizar.")
        return

    logger.info(f"Encontradas {len(new_movies)} películas para reenviar.")
    for msg in new_movies:
        file_name = extract_file_name(msg)
        caption = msg.text or file_name or "Película"
        try:
            # Enviamos como copia limpia en la nube de Telegram usando el file media
            await client.send_message(
                dest_chat,
                message=caption,
                file=msg.media
            )
            logger.info(f"✅ Película reenviada: {file_name or msg.id}")
            state["forwarded_message_ids"].append(msg.id)
            if msg.id > state["movies_last_id"]:
                state["movies_last_id"] = msg.id
            save_state(state)
            await asyncio.sleep(2.5)  # Pausa de cortesía para evitar FloodWait
        except Exception as e:
            logger.error(f"Error reenviando película ID {msg.id}: {e}")


async def get_or_create_forum_topic(client: TelegramClient, dest_chat, series_name: str, state: dict) -> Optional[int]:
    """Busca si ya existe un Tema en el supergrupo con el nombre de la serie; si no, lo crea."""
    normalized_name = series_name.strip().lower()
    
    # 1. Comprobar caché local
    cached_topics = state.setdefault("series_topics_cache", {})
    if normalized_name in cached_topics:
        return cached_topics[normalized_name]

    dest_input = await client.get_input_entity(dest_chat)

    # 2. Consultar temas existentes en el supergrupo de Telegram
    try:
        topics_res = await client(GetForumTopicsRequest(
            peer=dest_input,
            offset_date=None,
            offset_id=0,
            offset_topic=0,
            limit=100
        ))
        for topic in getattr(topics_res, "topics", []):
            t_title = getattr(topic, "title", "").strip().lower()
            t_id = getattr(topic, "id", None)
            if t_title and t_id:
                cached_topics[t_title] = t_id
                if t_title == normalized_name:
                    state["series_topics_cache"] = cached_topics
                    return t_id
    except Exception as e:
        logger.warning(f"No se pudieron listar los temas existentes: {e}")

    # 3. Si no existe, crear un nuevo tema para la serie
    try:
        logger.info(f"🆕 Creando nuevo Tema en el foro de Series: '{series_name}'...")
        rand_id = random.randint(1, 2**63 - 1)
        created = await client(CreateForumTopicRequest(
            peer=dest_input,
            title=series_name[:128],  # Límite de caracteres de Telegram
            random_id=rand_id
        ))
        
        # Obtener el ID del tema creado
        topic_id = None
        for update in getattr(created, "updates", []):
            msg = getattr(update, "message", None)
            if msg and hasattr(msg, "id"):
                action = getattr(msg, "action", None)
                if action and "TopicCreate" in type(action).__name__:
                    topic_id = msg.id
                    break
                elif topic_id is None:
                    topic_id = msg.id
            elif hasattr(update, "id"):
                topic_id = update.id

        if topic_id:
            logger.info(f"✅ Tema creado exitosamente para '{series_name}' (Topic ID: {topic_id})")
            cached_topics[normalized_name] = topic_id
            state["series_topics_cache"] = cached_topics
            save_state(state)
            return topic_id
        else:
            logger.error(f"No se pudo determinar el ID del tema creado para '{series_name}'")
    except Exception as e:
        logger.error(f"Error creando tema para '{series_name}': {e}")
        
    return None


async def sync_series(client: TelegramClient, state: dict):
    """Sincroniza series (carátula y episodios) hacia los temas del foro destino."""
    logger.info("--- INICIANDO SINCRONIZACIÓN DE SERIES ---")
    dest_chat = await client.get_input_entity(SERIES_DEST_CHAT)
    source_chat = await client.get_input_entity(SERIES_SOURCE_CHAT)
    
    last_id = state.get("series_last_id", 0)
    logger.info(f"Escaneando series nuevas posteriores al ID {last_id}...")
    
    # Leemos mensajes en orden cronológico (reverse=True)
    messages = []
    async for message in client.iter_messages(
        source_chat,
        reply_to=SERIES_SOURCE_TOPIC if SERIES_SOURCE_TOPIC else None,
        min_id=last_id,
        limit=60,
        reverse=True
    ):
        messages.append(message)

    if not messages:
        logger.info("No hay nuevos mensajes de series para procesar.")
        return

    current_series_title: Optional[str] = None
    current_topic_id: Optional[int] = None
    pending_poster = None

    for msg in messages:
        if msg.id in state.get("forwarded_message_ids", []):
            continue

        text_content = msg.text or ""
        file_name = extract_file_name(msg)
        
        # 1. Detectar si es una imagen de carátula o presentación
        if msg.media and isinstance(msg.media, MessageMediaPhoto):
            extracted = clean_series_title(text_content) if text_content else None
            if extracted and len(extracted) >= 3:
                current_series_title = extracted
                current_topic_id = await get_or_create_forum_topic(client, dest_chat, current_series_title, state)
                pending_poster = msg

        # 2. Detectar si es un video de episodio
        elif is_video_message(msg):
            # Si aún no tenemos título activo, deducirlo del nombre del archivo o del texto
            raw = text_content or file_name
            if not current_series_title and raw:
                extracted = clean_series_title(raw)
                if extracted and len(extracted) >= 3:
                    current_series_title = extracted
                    current_topic_id = await get_or_create_forum_topic(client, dest_chat, current_series_title, state)

            if current_topic_id:
                # Si había una carátula pendiente para este tema, enviarla primero
                if pending_poster:
                    try:
                        await client.send_message(
                            dest_chat,
                            message=pending_poster.text or f"Póster oficial - {current_series_title}",
                            file=pending_poster.media,
                            reply_to=current_topic_id
                        )
                        logger.info(f"🖼️ Póster enviado al tema '{current_series_title}'")
                        state["forwarded_message_ids"].append(pending_poster.id)
                        pending_poster = None
                        await asyncio.sleep(2)
                    except Exception as e:
                        logger.error(f"Error enviando póster: {e}")

                # Enviar el episodio al Tema correspondiente
                try:
                    caption = text_content or file_name or "Episodio"
                    await client.send_message(
                        dest_chat,
                        message=caption,
                        file=msg.media,
                        reply_to=current_topic_id
                    )
                    logger.info(f"🎬 Episodio enviado a '{current_series_title}': {file_name or msg.id}")
                    state["forwarded_message_ids"].append(msg.id)
                    await asyncio.sleep(2.5)
                except Exception as e:
                    logger.error(f"Error reenviando episodio ID {msg.id}: {e}")
            else:
                logger.warning(f"No se pudo determinar el tema destino para el video: {file_name or msg.id}")

        if msg.id > state["series_last_id"]:
            state["series_last_id"] = msg.id
        save_state(state)


async def main():
    if not STRING_SESSION:
        logger.error("❌ ERROR: La variable de entorno TELEGRAM_STRING_SESSION está vacía.")
        logger.error("Ejecuta 'python generar_sesion.py' primero para generar tu clave de sesión.")
        return

    logger.info("Iniciando cliente de Telegram con Telethon...")
    async with TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH) as client:
        me = await client.get_me()
        logger.info(f"Conectado como: {me.first_name} (@{me.username or 'sin_username'})")
        
        state = load_state()
        
        # 1. Sincronizar Películas
        try:
            await sync_movies(client, state)
        except Exception as e:
            logger.error(f"Fallo en sync_movies: {e}", exc_info=True)
            
        # 2. Sincronizar Series
        try:
            await sync_series(client, state)
        except Exception as e:
            logger.error(f"Fallo en sync_series: {e}", exc_info=True)
            
        logger.info("--- SINCRONIZACIÓN COMPLETADA CON ÉXITO ---")


if __name__ == "__main__":
    asyncio.run(main())
