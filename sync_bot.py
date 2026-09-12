import os
import re
import unicodedata
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
    CreateForumTopicRequest,
    DeleteTopicHistoryRequest
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


def clean_movie_title(raw_title: str, caption: str = "") -> str:
    """Extrae una clave normalizada de película para agrupar versiones duplicadas."""
    cand = ""
    if caption and len(caption.strip()) >= 3:
        first_line = caption.strip().split("\n")[0].strip()
        if 3 <= len(first_line) <= 150:
            cand = first_line
    if not cand:
        cand = raw_title

    # 1. Quitar extensiones, URLs y menciones
    text = re.sub(r"\.[a-zA-Z0-9]{2,4}$", "", cand)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[@#]\w+", "", text)

    # 2. Descomponer y eliminar acentos/diacríticos (ej: mí -> mi, único -> unico)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))

    # 3. Quitar emojis y caracteres gráficos especiales
    text = re.sub(r"[\U00010000-\U0010ffff]", "", text)
    text = re.sub(r"[\u2600-\u27bf\u2300-\u23ff\u2b50\u2b55\ufe0f]", "", text)

    # 4. Separar año pegado a letras (ej: Vaiana2026 -> Vaiana 2026)
    text = re.sub(r"([a-zA-Z])((?:19|20)\d\d)", r"\1 \2", text)

    # 5. Si tiene formato 'TITULO (Subtitulo o Alternativo)', aislar el título principal
    main_match = re.split(r"[\(\[]", text, maxsplit=1)
    if main_match and len(main_match[0].strip()) >= 3 and any(c.isalpha() for c in main_match[0]):
        title_cand = main_match[0]
    else:
        title_cand = text

    title_cand = title_cand.replace("_", " ").replace("-", " ").replace(".", " ")

    # 6. Extraer año si está en el título
    match = re.search(r"\b((?:19|20)\d\d)\b", title_cand)
    if match:
        title_part = title_cand[:match.start()].strip() or title_cand[match.end():].strip()
    else:
        title_part = title_cand

    # 7. Quitar prefijos comunes de subida ('Ver', 'Descargar', 'Estreno', 'Pelicula')
    title_part = re.sub(r"(?i)^(?:ver|descargar|estreno|pelicula)\s+", "", title_part.strip())

    # 8. Limpiar etiquetas típicas de ripeos, códecs, resoluciones, idiomas y grupos
    title_part = re.sub(
        r"(?i)\b(?:1080p?|720p?|2160p?|1038p?|4k|bdrip|brrip|dvdrip|web-?dl|webrip|bluray|hdtv|x264|h264|x265|h265|hevc|10bits|eac3|ac3|aac|dual|multi|forzados|completos|subs?|subtitulad[oa]s?|subtitulos|latino|castellano|espanol|cast|spa|ita|eng|es-?en|xusman|hdrip|by\s+\w+|hipolismata|para|rotulada|online|hdfull|hd|mp4|mkv|avi|25fps|5\.1|7\.1)\b",
        " ",
        title_part
    )
    title_part = re.sub(r"[\[\]\(\)\{\},.+:!¡?¿*=#~_]", " ", title_part)
    title_part = re.sub(r"\s+", " ", title_part).strip().lower()
    return title_part


def is_junk_series_title(title: str) -> bool:
    """Comprueba si un texto es solo un código de episodio/temporada o basura decorativa."""
    if not title or len(title.strip()) < 2:
        return True
    t = title.strip()
    # Si es solo código de episodio, temporada o números (ej. 1X01, S01E01, T1, 1x02, 1, 01)
    if re.match(r"(?i)^(?:S\d+(?:E\d+)?|T\d+(?:E\d+)?|\d+[xX]\d+|Cap[ií]tulo\s*\d+|Episodio\s*\d+|\d+|temporada\s*\d+)$", t):
        return True
    # Si solo tiene símbolos o decoradores
    if re.match(r"^[-–—:\s*=#~]+$", t):
        return True
    # Si no tiene al menos dos letras
    letters = [c for c in t if c.isalpha()]
    if len(letters) < 2:
        return True
    return False


def clean_series_title(raw_title: str) -> str:
    """Limpia el título para extraer únicamente el nombre base de la serie."""
    if not raw_title:
        return ""
        
    text = re.sub(r"\.[a-zA-Z0-9]{2,4}$", "", raw_title)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[@#]\w+", "", text)
    text = re.sub(r"\[.*?\]|\(.*?\)", "", text)
    
    # Quitar emojis comunes o símbolos residuales
    text = re.sub(r"[\U00010000-\U0010ffff]", "", text)
    
    # Reemplazar guiones bajos y puntos por espacios para respetar límites de palabras (\b)
    text = text.replace("_", " ").replace(".", " ")
    
    # Quitar créditos de ripeo, códecs, resoluciones, idiomas y etiquetas residuales
    text = re.sub(
        r"(?i)\b(?:1080p?|720p?|2160p?|4k|bdrip|brrip|dvdrip|web-?dl|webrip|bluray|hdtv|x264|h264|x265|h265|hevc|10bits|eac3|ac3|aac|dual|multi|forzados|completos|subs?|latino|castellano|español|cast|spa|ita|eng|subtitulado|xusman|hdrip|by\s+\w+|hipolismata|para|rotulada|final|completa|miniserie|precuela)\b",
        " ",
        text
    )
    
    # Cortar en patrones de temporada/episodio (ej. 1x01, 1X01, S01E01, Temporada 2, T 2, etc.)
    parts = re.split(
        r"(?i)\b(?:S\d+(?:E\d+)?|T\d+(?:E\d+)?|Temporada\s*\d+|\d+[xX]\d+|Cap[ií]tulo\s*\d+|Episodio\s*\d+|T\s*\d+)\b",
        text
    )
    candidates = [p.strip() for p in parts if p.strip()]
    
    title = ""
    if candidates:
        # Tomar el primer bloque que contenga letras y longitud válida
        for c in candidates:
            c_clean = re.sub(r"^[-–—:\s*=#~]+|[-–—:\s*=#~]+$", "", c).strip()
            c_clean = re.sub(r"(?i)^(?:esp|cast|lat|eng|spa)\s+", "", c_clean).strip()
            if len(c_clean) >= 2 and any(char.isalpha() for char in c_clean) and not is_junk_series_title(c_clean):
                title = c_clean
                break
    else:
        t_clean = re.sub(r"^[-–—:\s*=#~]+|[-–—:\s*=#~]+$", "", text).strip()
        if not is_junk_series_title(t_clean):
            title = t_clean
        
    title = re.sub(r"^[-–—:\s*=#~]+|[-–—:\s*=#~]+$", "", title).strip()
    title = re.sub(r"(?i)^(?:esp|cast|lat|eng|spa)\s+", "", title).strip()
    if is_junk_series_title(title):
        return ""
    return title.title()


def resolve_series_name(video_title: Optional[str], current_series_title: Optional[str]) -> Optional[str]:
    """Determina inteligentemente el nombre de la serie evitando confundir nombres de episodios."""
    if not video_title and current_series_title:
        return current_series_title
    if video_title and not current_series_title:
        return video_title
    if video_title and current_series_title:
        v_low = video_title.lower()
        c_low = current_series_title.lower()
        # Si uno está contenido en el otro (ej. "seinfeld" en "the seinfeld chronicles"),
        # el nombre de la serie oficial (póster) siempre tiene prioridad sobre el título del episodio
        if c_low in v_low or v_low in c_low:
            return current_series_title
        # Si el video tiene un nombre completamente distinto y válido, el video manda
        return video_title
    return None


async def cleanup_destination_duplicates(client: TelegramClient, dest_chat):
    """Escanea los mensajes recientes en el canal destino de películas y elimina versiones duplicadas de menor tamaño/calidad."""
    try:
        logger.info("Comprobando posibles películas duplicadas en el canal destino...")
        dest_input = await client.get_input_entity(dest_chat)
        
        recent_videos = []
        async for msg in client.iter_messages(dest_input, limit=60):
            if is_video_message(msg):
                recent_videos.append(msg)
                
        groups = defaultdict(list)
        for msg in recent_videos:
            fname = extract_file_name(msg)
            caption = msg.text or ""
            key = clean_movie_title(fname, caption)
            if len(key) >= 3:
                groups[key].append(msg)
                
        for key, msgs in groups.items():
            if len(msgs) > 1:
                # Ordenar por tamaño descendente (el más grande primero)
                sorted_msgs = sorted(msgs, key=lambda m: get_media_size(m), reverse=True)
                best_msg = sorted_msgs[0]
                to_delete = sorted_msgs[1:]
                del_ids = [m.id for m in to_delete]
                
                logger.info(f"🗑️ Eliminando {len(del_ids)} versión(es) repetida(s) de '{key}' en canal destino (conservando {get_media_size(best_msg)/(1024*1024):.1f} MB)...")
                await client.delete_messages(dest_input, del_ids)
                await asyncio.sleep(1)
    except Exception as e:
        logger.warning(f"No se pudo completar la limpieza de duplicados en destino: {e}")


async def sync_movies(client: TelegramClient, state: dict):
    """Sincroniza películas desde el grupo/tema origen hacia el canal destino."""
    logger.info("--- INICIANDO SINCRONIZACIÓN DE PELÍCULAS ---")
    dest_chat = await client.get_input_entity(MOVIES_DEST_CHAT)
    source_chat = await client.get_input_entity(MOVIES_SOURCE_CHAT)
    
    # 0. Limpiar posibles duplicados que ya se hayan enviado al canal destino
    await cleanup_destination_duplicates(client, dest_chat)

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
        caption_text = msg.text or ""
        title_key = clean_movie_title(fname, caption_text)
        # Si no se pudo limpiar bien, usar el nombre directo como clave
        key = title_key if len(title_key) >= 3 else (fname.lower() or str(msg.id))
        groups[key].append(msg)

    # 2. Seleccionar la mejor versión por cada grupo (mayor tamaño)
    raw_synced = state.setdefault("synced_movie_titles", [])
    synced_movie_titles = set(clean_movie_title(t) for t in raw_synced)
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


async def cleanup_spurious_topics(client: TelegramClient, dest_chat, state: dict):
    """Elimina temas vacíos, basura o duplicados de ejecuciones previas."""
    dest_input = await client.get_input_entity(dest_chat)
    
    # 1. Identificar y limpiar temas no deseados del caché local
    cached_topics = state.setdefault("series_topics_cache", {})
    junk_topic_ids = [5047, 5059, 5070, 5082, 5083, 5086, 5096, 5097, 5268, 5270, 5272, 5274, 5276, 5278, 5280, 5282, 5313]
    for k, v in list(cached_topics.items()):
        if v >= 5330 or v in junk_topic_ids or is_junk_series_title(k):
            junk_topic_ids.append(v)
            del cached_topics[k]
            logger.info(f"Limpiando tema no deseado del caché: '{k}' (ID {v})")
            
    state["series_topics_cache"] = cached_topics
    junk_topic_ids = list(set(junk_topic_ids))
    
    # 2. Eliminar temas no deseados en Telegram si aún existen
    for tid in junk_topic_ids:
        try:
            await client(DeleteTopicHistoryRequest(peer=dest_input, top_msg_id=tid))
            logger.info(f"🗑️ Tema no deseado ID {tid} eliminado de Telegram.")
            await asyncio.sleep(0.8)
        except Exception as e:
            logger.debug(f"Tema {tid} ya no existe o no se pudo eliminar: {e}")

    # 3. Escanear temas existentes en el supergrupo y borrar los que sean códigos de episodio o basura
    try:
        topics_res = await client(GetForumTopicsRequest(peer=dest_input, offset_date=None, offset_id=0, offset_topic=0, limit=100))
        for top in getattr(topics_res, "topics", []):
            top_title = getattr(top, "title", "").strip()
            top_id = getattr(top, "id", None)
            if top_id and top_id != 1 and is_junk_series_title(top_title):
                logger.info(f"🗑️ Eliminando tema basura detectado en Telegram: '{top_title}' (ID {top_id})...")
                await client(DeleteTopicHistoryRequest(peer=dest_input, top_msg_id=top_id))
                await asyncio.sleep(1)
    except Exception as e:
        logger.warning(f"Error escaneando temas en destino: {e}")


async def get_or_create_forum_topic(client: TelegramClient, dest_chat, series_name: str, state: dict) -> Optional[int]:
    """Busca si ya existe un Tema en el supergrupo con el nombre de la serie; si no, lo crea."""
    clean_name = clean_series_title(series_name)
    if not clean_name or is_junk_series_title(clean_name):
        logger.warning(f"Título de serie inválido o decorativo descartado: '{series_name}'")
        return None

    normalized_name = clean_name.strip().lower()
    
    # 1. Comprobar caché local
    cached_topics = state.setdefault("series_topics_cache", {})
    if normalized_name in cached_topics:
        return cached_topics[normalized_name]

    # Comprobar variaciones en la caché local
    for k, v in cached_topics.items():
        if clean_series_title(k).strip().lower() == normalized_name:
            cached_topics[normalized_name] = v
            return v

    dest_input = await client.get_input_entity(dest_chat)

    # 2. Consultar temas existentes en el supergrupo de Telegram paginando de 100 en 100
    matched_id = None
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
                t_raw = getattr(topic, "title", "").strip()
                t_id = getattr(topic, "id", None)
                if t_raw and t_id:
                    t_lower = t_raw.lower()
                    cached_topics[t_lower] = t_id
                    t_clean = clean_series_title(t_raw).lower()
                    if t_clean:
                        cached_topics[t_clean] = t_id
                        
                    if t_lower == normalized_name or t_clean == normalized_name:
                        matched_id = t_id
                        break
                    elif len(normalized_name) >= 4 and (normalized_name in t_lower or t_lower in normalized_name):
                        if matched_id is None:
                            matched_id = t_id

            if matched_id:
                break

            # Parámetros para la siguiente página
            last_topic = topics_list[-1]
            offset_topic = getattr(last_topic, "id", 0)
            offset_id = getattr(last_topic, "top_message", 0)
            offset_date = getattr(last_topic, "date", None)

            if len(topics_list) < 100:
                break

    except Exception as e:
        logger.warning(f"No se pudieron listar los temas existentes: {e}")

    if matched_id:
        cached_topics[normalized_name] = matched_id
        state["series_topics_cache"] = cached_topics
        return matched_id

    # 3. Si no existe, crear un nuevo tema para la serie
    try:
        logger.info(f"🆕 Creando nuevo Tema en el foro de Series: '{clean_name}'...")
        rand_id = random.randint(1, 2**63 - 1)
        created = await client(CreateForumTopicRequest(
            peer=dest_input,
            title=clean_name[:128],  # Límite de caracteres de Telegram
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
            logger.info(f"✅ Tema creado exitosamente para '{clean_name}' (Topic ID: {topic_id})")
            cached_topics[normalized_name] = topic_id
            state["series_topics_cache"] = cached_topics
            save_state(state)
            return topic_id
        else:
            logger.error(f"No se pudo determinar el ID del tema creado para '{clean_name}'")
    except Exception as e:
        logger.error(f"Error creando tema para '{clean_name}': {e}")
        
    return None


async def sync_series(client: TelegramClient, state: dict):
    """Sincroniza series (carátula y episodios) hacia los temas del foro destino."""
    logger.info("--- INICIANDO SINCRONIZACIÓN DE SERIES ---")
    dest_chat = await client.get_input_entity(SERIES_DEST_CHAT)
    source_chat = await client.get_input_entity(SERIES_SOURCE_CHAT)
    
    # 0. Limpiar temas basura o duplicados de ejecuciones previas
    await cleanup_spurious_topics(client, dest_chat, state)

    # Inspección de los mensajes alrededor del lote conflictivo
    try:
        inspect_msgs = await client.get_messages(source_chat, ids=list(range(157843, 157848)))
        for im in inspect_msgs:
            if im:
                logger.info(f"🔍 INSPECCIÓN ID {im.id}: media={type(im.media).__name__ if im.media else 'texto'}, text={repr(im.text)}")
    except Exception as e:
        logger.warning(f"Error inspeccionando mensajes: {e}")

    # 1. Escanear nuevos mensajes de series posteriores a series_last_id
    last_id = state.get("series_last_id", 0)
    logger.info(f"Escaneando series nuevas posteriores al ID {last_id}...")
    
    # Leemos mensajes en orden cronológico (reverse=True), aumentamos lote a 100 para no cortar series a la mitad
    messages = []
    async for message in client.iter_messages(
        source_chat,
        reply_to=SERIES_SOURCE_TOPIC if SERIES_SOURCE_TOPIC else None,
        min_id=last_id,
        limit=100,
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
        
        # 1. Detectar si es un mensaje de texto puro (anuncio o título de serie)
        if not msg.media and text_content:
            cand = clean_series_title(text_content)
            if cand and not is_junk_series_title(cand):
                current_series_title = cand
                logger.info(f"📝 Título de serie detectado en mensaje de texto: '{current_series_title}'")

        # 2. Detectar si es una imagen de carátula o presentación
        elif msg.media and isinstance(msg.media, MessageMediaPhoto):
            extracted = clean_series_title(text_content) if text_content else None
            # Si la foto tiene un título de serie válido, usarlo
            if extracted and not is_junk_series_title(extracted):
                current_series_title = extracted
                pending_poster = msg
                logger.info(f"🖼️ Póster detectado para serie: '{current_series_title}'")
            elif current_series_title:
                # Si la foto es un banner técnico (ej. 1080p.Castellano.T1) pero la serie ya fue declarada
                pending_poster = msg
                logger.info(f"🖼️ Póster técnico asociado a la serie activa: '{current_series_title}'")
            else:
                logger.info(f"Omitiendo foto decorativa o sin título válido: {repr(text_content[:40]) if text_content else msg.id}")

        # 3. Detectar si es un video de episodio
        elif is_video_message(msg):
            raw = file_name or text_content
            video_title = clean_series_title(raw) if raw else None
            if video_title and is_junk_series_title(video_title):
                video_title = None

            # Lógica estricta de asignación: Si hay una serie activa (ej. 'Seinfeld'), los capítulos pertenecen a ella
            target_series = None
            if current_series_title:
                if video_title and video_title.lower() != current_series_title.lower():
                    # Solo cambiar de serie si el video coincide con otra serie ya conocida en el foro
                    known_topics = state.get("series_topics_cache", {})
                    if video_title.lower() in known_topics:
                        target_series = video_title
                        current_series_title = target_series
                    else:
                        # Es el título de un capítulo (ej. 'The Library', 'The Cafe') -> se queda en la serie activa ('Seinfeld')
                        target_series = current_series_title
                else:
                    target_series = current_series_title
            else:
                target_series = video_title
                if target_series:
                    current_series_title = target_series

            target_topic_id = None
            if target_series and not is_junk_series_title(target_series):
                target_topic_id = await get_or_create_forum_topic(client, dest_chat, target_series, state)
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
