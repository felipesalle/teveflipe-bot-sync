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
    DeleteTopicHistoryRequest,
    EditForumTopicRequest
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
    if getattr(message, "file", None) and getattr(message.file, "name", None):
        return message.file.name or ""
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


KNOWN_VALID_NUMERIC_SERIES = {"24", "1883", "1923", "9-1-1", "300"}

SERIES_ALIASES = {
    "sobrenatural": "Supernatural",
    "supernatural ✓": "Supernatural",
    "the originals": "Los Originales",
    "los originales": "Los Originales",
    "bones": "Bones",
    "luna el misterio de calenda": "Luna, El Misterio De Calenda",
    "luna: el misterio de calenda": "Luna, El Misterio De Calenda",
    "luna, el misterio de calenda": "Luna, El Misterio De Calenda",
    "luna: el misterio de calenda ✓": "Luna, El Misterio De Calenda",
    "luna": "Luna, El Misterio De Calenda",
    "tierra amarga": "Tierra Amarga",
    "tierra amarga - emitido en tv": "Tierra Amarga",
    "tierra amarga emitido en tv": "Tierra Amarga",
    "entre fantasmas": "Entre Fantasmas",
    "ghost whisperer": "Entre Fantasmas",
    "decalogo": "Decálogo",
    "decálogo": "Decálogo",
    "el decalogo": "Decálogo",
    "el decálogo": "Decálogo",
    "los pilares de la tierra": "Los Pilares De La Tierra",
    "los pilares de la tierra 8 episodios": "Los Pilares De La Tierra",
    "dracula 3 episodios": "Dracula",
    "robots in disguise": "Transformers: Robots in Disguise",
    "transformers robots in disguise": "Transformers: Robots in Disguise",
    "beast wars 2 (jap)": "Transformers: Beast Wars II",
    "beast wars 2": "Transformers: Beast Wars II",
    "beast wars ii": "Transformers: Beast Wars II",
    "beast wars neo (jap)": "Transformers: Beast Wars Neo",
    "beast wars neo": "Transformers: Beast Wars Neo",
    "transformers g1": "Transformers (G1)",
    "transformers: generacion 1": "Transformers (G1)",
    "transformers generacion 1": "Transformers (G1)",
    "transformers headmasters": "Transformers: The Headmasters",
    "transformers the headmasters": "Transformers: The Headmasters",
    "transformers: the headmasters": "Transformers: The Headmasters",
    "the headmasters": "Transformers: The Headmasters",
    "transformers super-god masterforce": "Transformers: Super-God Masterforce",
    "transformers super god masterforce": "Transformers: Super-God Masterforce",
    "transformers: super-god masterforce": "Transformers: Super-God Masterforce",
    "transformers victory": "Transformers: Victory",
    "transformers: victory": "Transformers: Victory",
    "beast wars": "Transformers: Beast Wars",
    "transformers beast wars": "Transformers: Beast Wars",
    "beast machines": "Transformers: Beast Machines",
    "transformers beast machines": "Transformers: Beast Machines",
    "robot masters": "Transformers: Robot Masters",
    "transformers robot masters": "Transformers: Robot Masters",
    "halcon callejero": "Halcón Callejero",
    "halcón callejero": "Halcón Callejero",
    "el trueno azul": "El Trueno Azul",
    "el amor despues del amor": "El Amor Después del Amor",
    "el amor después del amor": "El Amor Después del Amor",
    "entourage": "Entourage",
    "entourage el séquito": "Entourage",
    "entourage el sequito": "Entourage",
}


def is_junk_series_title(title: str) -> bool:
    """Comprueba si un texto es solo un código de episodio/temporada o basura decorativa."""
    if not title or len(title.strip()) < 2:
        return True
    t = title.strip()
    if t.lower() in KNOWN_VALID_NUMERIC_SERIES:
        return False

    t_low = t.lower()
    if t_low in {
        "serie", "series", "serie de tv", "serie tv", "series tv",
        "audio", "completas", "leer", "fin 11", "en emision", "en emisión",
        "falta la", "titulo", "título", "sinopsis", "sss", "watch", "libro 1", "libro 2", "libro 3"
    }:
        return True

    # Si empieza con un número de episodio (ej. "01 - Protocolo De Batalla", "02 - ", "35 - ")
    m_num = re.match(r"^(\d{1,3})\s*[-–—.:_]\s*", t)
    if m_num and m_num.group(1) not in KNOWN_VALID_NUMERIC_SERIES:
        return True

    # Si es solo código de episodio, temporada o números (ej. 1X01, S01E01, T1, 1x02, 1×01, 1, 01, 111, etc.)
    if re.match(r"(?i)^(?:S\d+(?:E\d+)?|T\d+(?:E\d+)?|\d+[xX×\u00d7]\d+|Cap[iíãÃ\ufffd\xad\s]*tulo\s*\d+|Episodio\s*\d+|\d+|temporada\s*\d+)$", t):
        return True
    if re.match(r"(?i)^[▶►\s*]*(?:cap[iíãÃ\ufffd\xad\s]*tulo|episodio|temp(?:orada)?|parte|fin\s+de\s+serie)\b.*$", t):
        return True
    if re.match(r"(?i)^emitido\s+en\s+tv.*$", t):
        return True
    # Anuncios o separadores de temporada (ej. "Segunda Temporada", "▶️ Segunda Temporada", "Temporada 2", etc.)
    if re.match(r"(?i)^[▶►\s*]*(?:primera|segunda|tercera|cuarta|quinta|sexta|séptima|septima|octava|novena|décima|decima|última|ultima|\d+ª?)\s+temporada.*$", t):
        return True
    if re.match(r"(?i)^[▶►\s*]*temporada\s*(?:\d+|completa|final).*$", t):
        return True
    # Si solo tiene símbolos o decoradores
    if re.match(r"^[-–—:\s*=#~▶►]+$", t):
        return True
    # Si no tiene al menos dos letras
    letters = [c for c in t if c.isalpha()]
    if len(letters) < 2:
        return True
    return False


def is_series_allowed(series_title: Optional[str], msg_id: int, state: dict) -> bool:
    """Verifica si una serie está en la lista de permitidas (whitelist) o si es una serie nueva."""
    if not series_title:
        return False
        
    whitelist = state.get("series_whitelist", [])
    if not whitelist:
        return True  # Sin filtro activo, se permite todo
        
    backlog_cutoff = state.get("backlog_cutoff_id", 161650)
    auto_sync_new = state.get("auto_sync_new_series", True)
    
    # Si es contenido nuevo posterior al catálogo histórico y está activo el auto-sync, se acepta
    if auto_sync_new and msg_id > backlog_cutoff:
        return True
        
    s_low = series_title.lower().strip()
    for allowed in whitelist:
        a_low = allowed.lower().strip()
        if a_low in s_low or s_low in a_low:
            return True
            
    return False



def clean_series_title(raw_title: str, is_filename: bool = False) -> str:
    """Limpia el título para extraer únicamente el nombre base de la serie."""
    if not raw_title:
        return ""
        
    text = raw_title
    if not is_filename and "\n" in text:
        text = text.strip().split("\n")[0].strip()

    text = re.sub(r"\.[a-zA-Z0-9]{2,4}$", "", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[@#]\w+", "", text)
    text = re.sub(r"\[.*?\]|\(.*?\)", "", text)
    
    # Quitar emojis comunes o símbolos residuales
    text = re.sub(r"[\U00010000-\U0010ffff]", "", text)
    
    # Reemplazar guiones bajos, puntos y dos puntos por espacios para respetar límites de palabras (\b)
    text = text.replace("_", " ").replace(".", " ").replace(":", " ")
    
    # Comprobar alias exacto antes de podar
    raw_norm = text.lower().strip()
    for alias_key, canonical in SERIES_ALIASES.items():
        if raw_norm == alias_key:
            return canonical

    # En archivos de video, si el archivo empieza con código de episodio o número, NO contiene el nombre de la serie
    if is_filename:
        m_num = re.match(r"^\s*(\d{1,3})\s*[-–—.:_]\s*", text)
        if m_num and m_num.group(1) not in KNOWN_VALID_NUMERIC_SERIES:
            return ""
        if re.match(r"^(?:\d+[xX×\u00d7]\d+|[sS]\d+(?:[eE]\d+)?|[tT]\d+(?:[eE]\d+)?|cap(?:[iíãÃ\ufffd\xad\s]*tulo|\.)?\s*\d+|ep(?:isodio|\.)?\s*\d+)", text.strip(), re.I):
            return ""

    # Quitar frases descriptivas comunes en títulos de anuncios (ej. "- 1 Temporada Microhd", "- 5 Temporadas", etc.)
    text = re.sub(r"(?i)\s*[-–—:/|]+\s*\d+\s+tempora.*$", "", text)
    text = re.sub(r"(?i)\b\d+\s+tempora.*$", "", text)
    text = re.sub(r"(?i)\s*[-–—:/|]+\s*\d+\s+episodio.*$", "", text)
    text = re.sub(r"(?i)\b\d+\s+episodio.*$", "", text)
    text = re.sub(r"(?i)\b(?:finalizada|completa|miniserie|precuela)\b.*$", "", text)

    # Quitar extras, making-of, deleted scenes y tomas falsas que causan fragmentación
    text = re.sub(
        r"(?i)\s*[-–—:/|]*\s*\b(?:the\s+making\s+of|making\s+of|deleted\s+scenes?|gag\s+reel|featurette|behind\s+the\s+scenes|bloopers?|trailer|extras?)\b.*$",
        "",
        text
    )

    # Quitar cabeceras de temporada al inicio (ej. "▶️ Segunda Temporada", "Temporada 2", etc.)
    text = re.sub(r"(?i)^[▶►\s*]*(?:primera|segunda|tercera|cuarta|quinta|sexta|séptima|septima|octava|novena|décima|decima|última|ultima|\d+ª?)\s+temporada\s*[-–—:/|]*\s*", "", text)

    # Quitar créditos de ripeo, códecs, resoluciones, idiomas y etiquetas residuales
    text = re.sub(
        r"(?i)\b(?:1080p?|720p?|2160p?|4k|bdrip|brrip|dvdrip|web-?dl|webrip|bluray|hdtv|x264|h264|x265|h265|hevc|10bits|eac3|ac3|aac|dual|multi|forzados|completos|subs?|latino|castellano|español|cast|spa|ita|eng|subtitulado|xusman|hdrip|by\s+\w+|hipolismata|para|rotulada)\b",
        " ",
        text
    )
    
    # Quitar fechas de emisión (ej. 08-07-22, 08/07/2022, 2022-07-08)
    text = re.sub(r"\b\d{1,2}[-–/]\d{1,2}[-–/]\d{2,4}\b", " ", text)
    text = re.sub(r"\b\d{4}[-–/]\d{1,2}[-–/]\d{1,2}\b", " ", text)

    # Cortar en patrones de temporada/episodio (ej. 1x01, 1X01, 1×01, S01E01, Temporada 2, T 2, y códigos 01 -, 101, 111, 120...)
    parts = re.split(
        r"(?i)\b(?:S\d+(?:E\d+)?|T\d+(?:E\d+)?|Temporada\s*\d+|\d+[xX×\u00d7]\d+|Cap(?:[iíãÃ\ufffd\xad\s]*tulo|\.)?\s*\d+|Ep(?:isodio|\.)?\s*\d+|Parte\s*\d+|T\s*\d+|\b\d{1,2}\s*[-–—]|\b\d{1,2}\s*(?:TV|VOSE|HD)\b|\b[1-9]\d{2}\b)\b",
        text
    )
    
    title = ""
    if is_filename:
        # En archivos de video, el nombre de serie normalmente precede al episodio (ej. 'Penny Dreadful 1x01').
        before_ep = parts[0].strip() if parts else ""
        c_clean = re.sub(r"^[-–—:\s*=#~▶►]+|[-–—:\s*=#~▶►]+$", "", before_ep).strip()
        c_clean = re.sub(r"(?i)^(?:esp|cast|lat|eng|spa)\s+", "", c_clean).strip()
        if c_clean.lower() not in KNOWN_VALID_NUMERIC_SERIES:
            c_clean = re.sub(r"\s+\d{1,2}$", "", c_clean).strip()
        is_numeric = c_clean.lower() in KNOWN_VALID_NUMERIC_SERIES
        if len(c_clean) >= 2 and (any(char.isalpha() for char in c_clean) or is_numeric) and not is_junk_series_title(c_clean):
            title = c_clean
        elif len(parts) > 1:
            # En formatos españoles donde el archivo empieza por el número (ej. '1x12_Luna_El_Misterio_de_Calenda.avi')
            after_ep = parts[1].strip()
            a_clean = re.sub(r"^[-–—:\s*=#~▶►]+|[-–—:\s*=#~▶►]+$", "", after_ep).strip()
            a_clean = re.sub(r"(?i)^(?:esp|cast|lat|eng|spa)\s+", "", a_clean).strip()
            if a_clean.lower() not in KNOWN_VALID_NUMERIC_SERIES:
                a_clean = re.sub(r"\s+\d{1,2}$", "", a_clean).strip()
            if a_clean.lower() in SERIES_ALIASES:
                title = a_clean
            else:
                return ""
        else:
            return ""
    else:
        # En mensajes de texto y pósters, buscar el primer candidato con texto válido
        candidates = [p.strip() for p in parts if p.strip()]
        if candidates:
            for c in candidates:
                c_clean = re.sub(r"^[-–—:\s*=#~▶►]+|[-–—:\s*=#~▶►]+$", "", c).strip()
                c_clean = re.sub(r"(?i)^(?:esp|cast|lat|eng|spa)\s+", "", c_clean).strip()
                if c_clean.lower() not in KNOWN_VALID_NUMERIC_SERIES:
                    c_clean = re.sub(r"\s+\d{1,2}$", "", c_clean).strip()
                is_numeric = c_clean.lower() in KNOWN_VALID_NUMERIC_SERIES
                if len(c_clean) >= 2 and (any(char.isalpha() for char in c_clean) or is_numeric) and not is_junk_series_title(c_clean):
                    title = c_clean
                    break
        else:
            t_clean = re.sub(r"^[-–—:\s*=#~▶►]+|[-–—:\s*=#~▶►]+$", "", text).strip()
            if t_clean.lower() not in KNOWN_VALID_NUMERIC_SERIES:
                t_clean = re.sub(r"\s+\d{1,2}$", "", t_clean).strip()
            if not is_junk_series_title(t_clean):
                title = t_clean
        
    title = re.sub(r"^[-–—:\s*=#~▶►]+|[-–—:\s*=#~▶►]+$", "", title).strip()
    title = re.sub(r"(?i)^(?:esp|cast|lat|eng|spa)\s+", "", title).strip()
    title = re.sub(r"\s+", " ", title).strip()
    if is_junk_series_title(title):
        return ""
        
    norm = title.lower().strip()
    for alias_key, canonical in SERIES_ALIASES.items():
        if norm == alias_key or norm.startswith(alias_key + " ") or norm.startswith(alias_key + "_") or norm.startswith(alias_key + "-") or norm.startswith(alias_key + " -"):
            return canonical
        
    return title.title()



def resolve_series_name(video_title: Optional[str], current_series_title: Optional[str]) -> Optional[str]:
    """Determina inteligentemente el nombre de la serie evitando confundir nombres de episodios."""
    if current_series_title and is_junk_series_title(current_series_title):
        current_series_title = None
    if video_title and is_junk_series_title(video_title):
        video_title = None

    if not video_title and current_series_title:
        return current_series_title
    if video_title and not current_series_title:
        return video_title
    if video_title and current_series_title:
        v_low = video_title.lower()
        c_low = current_series_title.lower()
        if c_low == v_low:
            return current_series_title
        # Si uno está contenido en el otro (ej. "seinfeld" en "the seinfeld chronicles"),
        # el nombre de la serie oficial (póster) siempre tiene prioridad sobre el título del episodio
        if c_low in v_low:
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


KNOWN_JUNK_TOPIC_IDS = {
    5047, 5059, 5070, 5082, 5083, 5086, 5096, 5097, 
    5268, 5270, 5272, 5274, 5276, 5278, 5280, 5282, 5313,
    5525, 5676, 5700, 5707, 5764, 5793,
    9773, 9782, 9784, 9786, 9792, 9794, 9796, 9801
} | set(range(5327, 5430))


async def cleanup_spurious_topics(client: TelegramClient, dest_chat, state: dict):
    """Elimina temas vacíos, basura o duplicados de ejecuciones previas."""
    dest_input = await client.get_input_entity(dest_chat)
    
    # 1. Identificar y limpiar temas no deseados del caché local
    cached_topics = state.setdefault("series_topics_cache", {})
    junk_topic_ids = set(KNOWN_JUNK_TOPIC_IDS)
    for k, v in list(cached_topics.items()):
        if v in junk_topic_ids or is_junk_series_title(k):
            junk_topic_ids.add(v)
            del cached_topics[k]
            logger.info(f"Limpiando tema no deseado del caché: '{k}' (ID {v})")
            
    state["series_topics_cache"] = cached_topics
    
    # 2. Eliminar temas no deseados en Telegram si aún existen
    for tid in sorted(junk_topic_ids):
        try:
            await client(DeleteTopicHistoryRequest(peer=dest_input, top_msg_id=tid))
            logger.info(f"🗑️ Tema no deseado ID {tid} eliminado de Telegram.")
            await asyncio.sleep(0.4)
        except Exception:
            pass

    # Renombrar tema 6031 si tenía título largo con coletillas
    try:
        await client(EditForumTopicRequest(peer=dest_input, topic_id=6031, title="24 Legacy"))
    except Exception:
        pass

    # 3. Escanear temas existentes en el supergrupo y borrar los que sean códigos de episodio o basura
    try:
        topics_res = await client(GetForumTopicsRequest(peer=dest_input, offset_date=None, offset_id=0, offset_topic=0, limit=100))
        for top in getattr(topics_res, "topics", []):
            top_title = getattr(top, "title", "").strip()
            top_id = getattr(top, "id", None)
            if top_id and top_id != 1 and (is_junk_series_title(top_title) or top_id in junk_topic_ids):
                logger.info(f"🗑️ Eliminando tema basura detectado en Telegram: '{top_title}' (ID {top_id})...")
                try:
                    await client(DeleteTopicHistoryRequest(peer=dest_input, top_msg_id=top_id))
                    await asyncio.sleep(0.5)
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"Error escaneando temas en destino: {e}")


async def get_or_create_forum_topic(client: TelegramClient, dest_chat, series_name: str, state: dict) -> Optional[int]:
    """Busca si ya existe un Tema en el supergrupo con el nombre de la serie; si no, lo crea."""
    clean_name = clean_series_title(series_name, is_filename=False)
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
        if clean_series_title(k, is_filename=False).strip().lower() == normalized_name:
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
                    if t_id in KNOWN_JUNK_TOPIC_IDS or is_junk_series_title(t_raw):
                        continue
                    t_lower = t_raw.lower()
                    cached_topics[t_lower] = t_id
                    t_clean = clean_series_title(t_raw, is_filename=False).lower()
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
    
    # Leemos mensajes en orden cronológico (reverse=True), aumentamos lote a 600 para avanzar rápido en descartes
    messages = []
    async for message in client.iter_messages(
        source_chat,
        reply_to=SERIES_SOURCE_TOPIC if SERIES_SOURCE_TOPIC else None,
        min_id=last_id,
        limit=600,
        reverse=True
    ):
        messages.append(message)

    if not messages:
        logger.info("No hay nuevos mensajes de series para procesar.")
        return

    current_series_title: Optional[str] = state.get("current_series_title")
    current_topic_id: Optional[int] = state.get("current_topic_id")
    pending_poster = None

    for msg in messages:
        if msg.id in state.get("forwarded_message_ids", []):
            continue

        text_content = msg.text or ""
        file_name = extract_file_name(msg)
        
        # 1. Detectar si es un mensaje de texto puro (anuncio o título de serie)
        if not msg.media and text_content:
            cand = clean_series_title(text_content, is_filename=False)
            if cand and not is_junk_series_title(cand):
                current_series_title = cand
                state["current_series_title"] = current_series_title
                current_topic_id = None  # No crear tema hasta que llegue video!
                logger.info(f"📝 Título de serie detectado en mensaje de texto (esperando video): '{current_series_title}'")

        # 2. Detectar si es una imagen de carátula o presentación
        elif msg.media and isinstance(msg.media, MessageMediaPhoto):
            extracted = clean_series_title(text_content, is_filename=False) if text_content else None
            # Si la foto tiene un título de serie válido, usarlo
            if extracted and not is_junk_series_title(extracted):
                current_series_title = extracted
                state["current_series_title"] = current_series_title
                current_topic_id = None  # No crear tema hasta que llegue video!
                pending_poster = msg
                logger.info(f"🖼️ Póster detectado para serie (esperando video): '{current_series_title}'")
            elif current_series_title:
                # Si la foto es un banner técnico (ej. 1080p.Castellano.T1) pero la serie ya fue declarada y permitida
                pending_poster = msg
                logger.info(f"🖼️ Póster técnico asociado a la serie activa: '{current_series_title}'")
            else:
                logger.debug(f"Omitiendo foto decorativa o no seleccionada: {repr(text_content[:40]) if text_content else msg.id}")

        # 3. Detectar si es un video de episodio
        elif is_video_message(msg):
            # Obtener el nombre de serie del archivo o de la descripción del video
            video_series_title = clean_series_title(file_name, is_filename=True) if file_name else None
            if not video_series_title and text_content:
                # Solo usar caption si no parece código de episodio o nombre de archivo
                if not re.match(r"^\s*\d{1,3}\s*[-–—.:_]", text_content.strip()):
                    video_series_title = clean_series_title(text_content, is_filename=False)
            if video_series_title and is_junk_series_title(video_series_title):
                video_series_title = None

            # Si el video tiene un nombre explícito de serie diferente de la activa
            if video_series_title:
                resolved = resolve_series_name(video_series_title, current_series_title)
                if resolved and resolved.lower() != (current_series_title or "").lower():
                    logger.info(f"🔄 Cambio de serie detectado por video: '{current_series_title}' -> '{resolved}'")
                    current_series_title = resolved
                    state["current_series_title"] = current_series_title
                    current_topic_id = None

            if current_series_title and is_junk_series_title(current_series_title):
                current_series_title = ""
                current_topic_id = None
                state["current_series_title"] = ""
                state["current_topic_id"] = None

            target_series = current_series_title
            if not target_series or not is_series_allowed(target_series, msg.id, state):
                if msg.id > state.get("series_last_id", 0):
                    state["series_last_id"] = msg.id
                save_state(state)
                continue

            # Crear o buscar tema SOLO aquí, cuando realmente tenemos un episodio de video para enviar
            if not current_topic_id:
                current_topic_id = await get_or_create_forum_topic(client, dest_chat, target_series, state)
                state["current_topic_id"] = current_topic_id

            target_topic_id = current_topic_id

            if not target_topic_id:
                logger.warning(f"Omitiendo video huérfano sin serie identificada: {file_name or msg.id}")
                if msg.id > state.get("series_last_id", 0):
                    state["series_last_id"] = msg.id
                save_state(state)
                continue

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
                    state.setdefault("forwarded_message_ids", []).append(pending_poster.id)
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
                state.setdefault("forwarded_message_ids", []).append(msg.id)
                await asyncio.sleep(2.5)
            except Exception as e:
                logger.error(f"Error reenviando episodio ID {msg.id}: {e}")

        if msg.id > state.get("series_last_id", 0):
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
