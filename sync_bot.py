import os
import re
import json
import asyncio
import logging
from typing import Optional, Dict, List
from collections import defaultdict
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
        "synced_movie_titles": [],   # Lista de títulos de películas ya sincronizadas
        "forwarded_message_ids": []
    }


def save_state(state: dict):
    try:
        # Mantener listas acotadas para no saturar el archivo de estado
        if len(state.get("forwarded_message_ids", [])) > 5000:
            state["forwarded_message_ids"] = state["forwarded_message_ids"][-5000:]
        if len(state.get("synced_movie_titles", [])) > 5000:
            state["synced_movie_titles"] = state["synced_movie_titles"][-5000:]
            
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


def get_media_size(message) -> int:
    """Obtiene el tamaño en bytes del archivo del mensaje."""
    if getattr(message, "file", None) and hasattr(message.file, "size"):
        return message.file.size or 0
    if message.media and isinstance(message.media, MessageMediaDocument) and message.media.document:
        return getattr(message.media.document, "size", 0) or 0
    return 0


def clean_movie_title(raw_title: str) -> str:
    """Extrae una clave normalizada de película para agrupar versiones duplicadas."""
    text = re.sub(r"\.[a-zA-Z0-9]{2,4}$", "", raw_title)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"@\w+", "", text)
    text = text.replace("_", " ").replace("-", " ")
    
    # Extraer año si existe (ej. 1999, 2024, etc.)
    match = re.search(r"\b((?:19|20)\d\d)\b", text)
    if match:
        title_part = text[:match.start()].strip() or text[match.end():].strip()
    else:
        title_part = text

    # Limpiar etiquetas típicas de ripeos, códecs y audios
    title_part = re.sub(
        r"(?i)\b(?:1080p|720p|2160p|4k|bdrip|brrip|dvdrip|web-?dl|webrip|bluray|x264|h264|x265|h265|hevc|eac3|ac3|aac|dual|multi|forzados|completos|subs?|latino|castellano|español|cast|spa|ita|eng|subtitulado|xusman|hdrip)\b",
        "",
        title_part
    )
    title_part = re.sub(r"[\[\]\(\)\{\},.+:!¡?¿]", " ", title_part)
    title_part = re.sub(r"\s+", " ", title_part).strip().lower()
    return title_part


def clean_series_title(raw_title: str) -> str:
    """Limpia el título para extraer únicamente el nombre base de la serie."""
    text = re.sub(r"\.[a-zA-Z0-9]{2,4}$", "", raw_title)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"\[.*?\]|\(.*?\)", "", text)
    
    # Cortar en patrones de temporada/episodio (ej. 1x01, S01E01, Temporada 2, etc.)
    parts = re.split(
        r"(?i)\b(?:S\d+(?:E\d+)?|T\d+(?:E\d+)?|Temporada\s*\d+|\d+x\d+|Cap[ií]tulo\s*\d+|Episodio\s*\d+)\b",
        text
    )
    candidates = [p.replace(".", " ").replace("_", " ").strip() for p in parts if p.strip()]
    
    title = ""
    if candidates:
        # Tomar el primer bloque que contenga letras y longitud válida
        for c in candidates:
            c_clean = re.sub(r"^[-–—:\s]+|[-–—:\s]+$", "", c).strip()
            if len(c_clean) >= 2 and any(char.isalpha() for char in c_clean):
                title = c_clean
                break
        if not title:
            title = candidates[0]
    else:
        title = text
        
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

    logger.info(f"Se encontraron {len(new_movies)} archivos de video de películas.")

    # 1. Agrupar mensajes por título normalizado de la película
    groups = defaultdict(list)
    for msg in new_movies:
        fname = extract_file_name(msg)
        raw_text = msg.text or fname
        title_key = clean_movie_title(raw_text)
        # Si no se pudo limpiar bien, usar el nombre directo como clave
        key = title_key if len(title_key) >= 3 else (fname.lower() or str(msg.id))
        groups[key].append(msg)

    # 2. Seleccionar la mejor versión por cada grupo (mayor tamaño)
    synced_movie_titles = set(state.setdefault("synced_movie_titles", []))
    movies_to_forward = []
    for key, msgs in groups.items():
        if key in synced_movie_titles:
            logger.info(f"⏭️ Película '{key}' ya fue reenviada anteriormente. Omitiendo versiones duplicadas.")
            for m in msgs:
                state["forwarded_message_ids"].append(m.id)
                if m.id > state["movies_last_id"]:
                    state["movies_last_id"] = m.id
            continue

        best_msg = max(msgs, key=lambda m: get_media_size(m))
        movies_to_forward.append((key, best_msg, msgs))

    logger.info(f"Películas únicas a reenviar tras desduplicación: {len(movies_to_forward)}")

    for key, best_msg, all_msgs in movies_to_forward:
        file_name = extract_file_name(best_msg)
        file_size_mb = get_media_size(best_msg) / (1024 * 1024)
        caption = best_msg.text or file_name or "Película"
        
        try:
            # Enviamos como copia limpia en la nube de Telegram usando el file media
            await client.send_message(
                dest_chat,
                message=caption,
                file=best_msg.media
            )
            logger.info(f"✅ Película reenviada: {file_name or best_msg.id} ({file_size_mb:.1f} MB)")
            
            # Registrar todos los mensajes del grupo como procesados para no reenviar versiones alternas
            for m in all_msgs:
                state["forwarded_message_ids"].append(m.id)
                if m.id > state["movies_last_id"]:
                    state["movies_last_id"] = m.id
                    
            state["synced_movie_titles"].append(key)
            save_state(state)
            await asyncio.sleep(2.5)  # Pausa de cortesía para evitar FloodWait
        except Exception as e:
            logger.error(f"Error reenviando película ID {best_msg.id}: {e}")


async def get_or_create_forum_topic(client: TelegramClient, dest_chat, series_name: str, state: dict) -> Optional[int]:
    """Busca si ya existe un Tema en el supergrupo con el nombre de la serie; si no, lo crea."""
    normalized_name = series_name.strip().lower()
    
    # 1. Comprobar caché local
    cached_topics = state.setdefault("series_topics_cache", {})
    if normalized_name in cached_topics:
        return cached_topics[normalized_name]

    dest_input = await client.get_input_entity(dest_chat)

    # 2. Consultar temas existentes en el supergrupo de Telegram paginando de 100 en 100
    try:
        offset_date = None
        offset_id = 0
        offset_topic = 0
        
        while True:
            topics_res = await client(GetForumTopicsRequest(
                peer=dest_input,
                offset_date=offset_date,
                offset_id=offset_id,
                offset_topic=offset_topic,
                limit=100
            ))
            
            topics_list = getattr(topics_res, "topics", [])
            if not topics_list:
                break
                
            for topic in topics_list:
                t_title = getattr(topic, "title", "").strip().lower()
                t_id = getattr(topic, "id", None)
                if t_title and t_id:
                    cached_topics[t_title] = t_id
                    if t_title == normalized_name:
                        state["series_topics_cache"] = cached_topics
                        return t_id

            # Parámetros para la siguiente página
            last_topic = topics_list[-1]
            offset_topic = getattr(last_topic, "id", 0)
            offset_id = getattr(last_topic, "top_message", 0)
            offset_date = getattr(last_topic, "date", None)

            if len(topics_list) < 100:
                break

    except Exception as e:
        logger.warning(f"No se pudieron listar los temas existentes: {e}")

    # Si ya se encontró durante la búsqueda
    if normalized_name in cached_topics:
        state["series_topics_cache"] = cached_topics
        return cached_topics[normalized_name]

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
            if extracted and len(extracted) >= 2:
                current_series_title = extracted
                current_topic_id = await get_or_create_forum_topic(client, dest_chat, current_series_title, state)
                pending_poster = msg

        # 2. Detectar si es un video de episodio
        elif is_video_message(msg):
            raw = text_content or file_name
            video_title = clean_series_title(raw) if raw else None

            # Siempre resolver el tema adecuado según el título del video o el actual
            target_series = video_title or current_series_title
            target_topic_id = None

            if target_series and len(target_series) >= 2:
                target_topic_id = await get_or_create_forum_topic(client, dest_chat, target_series, state)
                current_series_title = target_series
                current_topic_id = target_topic_id
            elif current_topic_id:
                target_topic_id = current_topic_id

            if target_topic_id:
                # Si había una carátula pendiente para este tema, enviarla primero
                if pending_poster and current_series_title:
                    try:
                        await client.send_message(
                            dest_chat,
                            message=pending_poster.text or f"Póster oficial - {current_series_title}",
                            file=pending_poster.media,
                            reply_to=target_topic_id
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
                        reply_to=target_topic_id
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
