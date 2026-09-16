import asyncio
import json
import logging
import os
import random
import re
import sys
import unicodedata
from typing import Optional, Tuple

from telethon import TelegramClient, errors, utils
from telethon.sessions import StringSession
from telethon.tl.functions.channels import CreateChannelRequest
from telethon.tl.functions.messages import ExportChatInviteRequest
from telethon.tl.types import (
    MessageMediaDocument,
    DocumentAttributeVideo,
    DocumentAttributeFilename,
    ChatInviteExported
)

logging.basicConfig(
    format="[%(asctime)s] %(levelname)s - %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("SyncCine80y90")

# Credenciales de Telegram
API_ID = int(os.getenv("TELEGRAM_API_ID") or 0)
API_HASH = os.getenv("TELEGRAM_API_HASH") or ""
STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION") or ""

# Canal Origen: Grupo fuente oficial (-1001905652210 tema 1605935)
SOURCE_CHAT_ID = int(os.getenv("MOVIES_80_90_SOURCE_CHAT", "-1001905652210"))
SOURCE_TOPIC_ID = int(os.getenv("MOVIES_80_90_SOURCE_TOPIC", "1605935"))

TARGET_GROUP_TITLE = os.getenv("MOVIES_80_90_TARGET_TITLE", "Cine de los 80 y 90")
STATE_FILE = "sync_state_80_90.json"
MORE_MARKER = ".more_80_90"

# Rango de Años: Décadas de 1980 y 1990
MIN_YEAR = 1980
MAX_YEAR = 1999

# Límites de ejecución por tanda
BATCH_FORWARD_LIMIT = int(os.getenv("BATCH_FORWARD_LIMIT", "50"))
MAX_MESSAGES_TO_SCAN = int(os.getenv("MAX_MESSAGES_TO_SCAN", "20000"))


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Error cargando {STATE_FILE}: {e}")
    return {
        "dest_chat_id": 0,
        "dest_invite_link": "",
        "forwarded_titles": [],
        "forwarded_msg_ids": [],
        "total_synced": 0,
        "last_message_id_scanned": 0,
        "highest_id_scanned": 0
    }


def save_state(state: dict):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error guardando {STATE_FILE}: {e}")


def extract_movie_year(raw_text: str) -> Optional[int]:
    """
    Extrae el año de producción de una película a partir del texto y nombre del archivo.
    """
    if not raw_text:
        return None

    # 1. Metadatos explícitos: "Año: 1985", "Estreno: 1994", "Year: 1989"
    explicit_match = re.search(r'(?i)\b(?:a[ñn]o|year|estreno|fecha|lan[zç]amiento)[:\s]+(\d{4})\b', raw_text)
    if explicit_match:
        y = int(explicit_match.group(1))
        if 1888 <= y <= 2030:
            return y

    # 2. Limpiar resoluciones y códecs comunes
    cleaned = re.sub(r'(?i)\b(?:1080p?|1080i|720p?|2160p?|480p?|576p?|x264|x265|h264|h265|5\.1|7\.1)\b', ' ', raw_text)

    # 3. Año entre paréntesis o corchetes: (1985), [1994]
    bracket_match = re.search(r'[\(\[]\s*(\b1[89]\d{2}|20\d{2}\b)\s*[\)\]]', cleaned)
    if bracket_match:
        y = int(bracket_match.group(1))
        if 1888 <= y <= 2030:
            return y

    # 4. Delimitado por guiones, puntos o espacios: .1985., _1994_, - 1989 -
    delimiters_match = re.search(r'(?:[._\-\s])(1[89]\d{2}|20\d{2})(?:[._\-\s]|$)', cleaned)
    if delimiters_match:
        y = int(delimiters_match.group(1))
        if 1888 <= y <= 2030:
            return y

    # 5. Número de 4 dígitos aislado
    general_match = re.search(r'\b(1[89]\d{2}|20\d{2})\b', cleaned)
    if general_match:
        y = int(general_match.group(1))
        if 1888 <= y <= 2030:
            return y

    return None


def normalize_movie_title(raw_title: str, caption: str = "") -> str:
    """
    Genera una clave normalizada de película para deduplicación.
    """
    cand = ""
    if caption:
        title_match = re.search(r'(?i)(?:t[ií]tulo|pel[ií]cula)[:\s]+([^\n\r]+)', caption)
        if title_match:
            cand = title_match.group(1).strip()
        else:
            first_line = caption.strip().split("\n")[0].strip()
            if not re.match(r'(?i)^(?:a[ñn]o|year|estreno|director|reparto|sinopsis|duraci[oó]n|g[eé]nero)[:\s]', first_line):
                if 3 <= len(first_line) <= 120 and not first_line.lower().startswith(("http", "t.me", "ver ", "descargar ")):
                    cand = first_line

    if not cand:
        cand = raw_title

    # Quitar extensiones y URLs
    text = re.sub(r"\.[a-zA-Z0-9]{2,4}$", "", cand)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[@#]\w+", "", text)

    # Descomponer y eliminar acentos
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))

    # Quitar emojis
    text = re.sub(r"[\U00010000-\U0010ffff]", "", text)
    text = re.sub(r"[\u2600-\u27bf\u2300-\u23ff\u2b50\u2b55\ufe0f]", "", text)

    # Aislar título de paréntesis
    parts = re.split(r"[\(\[]", text, maxsplit=1)
    if parts and len(parts[0].strip()) >= 2 and any(c.isalpha() for c in parts[0]):
        title_cand = parts[0]
    else:
        title_cand = text

    title_cand = title_cand.replace("_", " ").replace("-", " ").replace(".", " ")
    title_cand = re.sub(r"\b(1[89]\d{2}|20\d{2})\b", " ", title_cand)
    title_cand = re.sub(
        r"(?i)\b(?:1080p?|720p?|2160p?|4k|bdrip|brrip|dvdrip|web-?dl|webrip|bluray|hdtv|x264|h264|x265|h265|hevc|ac3|aac|dual|multi|castellano|latino|espanol|vose|sub|subtitulado|hdrip|mkv|mp4|avi)\b",
        " ",
        title_cand
    )
    title_cand = re.sub(r"[\[\]\(\)\{\},.+:!¡?¿*=#~_]", " ", title_cand)
    return re.sub(r"\s+", " ", title_cand).strip().lower()


def is_target_movie_video(message) -> Tuple[bool, str]:
    """
    Verifica si el mensaje contiene un archivo multimedia de video.
    Excluye archivos comprimidos (.rar, .zip) y audios.
    """
    if not message or not message.media:
        return False, ""

    fname = ""
    if getattr(message, "file", None) and getattr(message.file, "name", None):
        fname = message.file.name or ""

    if not fname and isinstance(message.media, MessageMediaDocument) and message.media.document:
        for attr in message.media.document.attributes:
            if isinstance(attr, DocumentAttributeFilename):
                fname = attr.file_name or ""
                break

    fname_lower = fname.lower()

    if fname_lower.endswith((".rar", ".zip", ".7z", ".tar", ".gz", ".mp3", ".flac", ".wav", ".pdf", ".txt")):
        return False, fname

    is_video = False
    if getattr(message, "video", None):
        is_video = True
    elif isinstance(message.media, MessageMediaDocument) and message.media.document:
        doc = message.media.document
        if doc.mime_type and doc.mime_type.startswith("video/"):
            is_video = True
        for attr in doc.attributes:
            if isinstance(attr, DocumentAttributeVideo):
                is_video = True
                break
            if isinstance(attr, DocumentAttributeFilename):
                if attr.file_name and attr.file_name.lower().endswith((".mkv", ".mp4", ".avi", ".mov", ".webm", ".ts", ".m4v")):
                    is_video = True
                    break

    if is_video:
        return True, fname

    return False, fname


def get_media_size(message) -> int:
    if getattr(message, "file", None) and hasattr(message.file, "size"):
        return message.file.size or 0
    if message.media and isinstance(message.media, MessageMediaDocument) and message.media.document:
        return getattr(message.media.document, "size", 0) or 0
    return 0


async def get_or_create_target_group(client: TelegramClient, state: dict):
    # 1. Por ID guardado
    saved_chat_id = state.get("dest_chat_id")
    if saved_chat_id and saved_chat_id != 0:
        try:
            entity = await client.get_entity(saved_chat_id)
            logger.info(f"✅ Grupo destino conectado: '{getattr(entity, 'title', '')}' (ID {saved_chat_id})")
            return entity
        except Exception as e:
            logger.warning(f"Aviso conectando grupo ID {saved_chat_id}: {e}")

    # 2. Buscar en diálogos
    async for dialog in client.iter_dialogs(limit=150):
        if (dialog.is_channel or dialog.is_group) and dialog.title:
            if dialog.title.strip().lower() == TARGET_GROUP_TITLE.strip().lower():
                entity = dialog.entity
                dest_id = utils.get_peer_id(entity)
                state["dest_chat_id"] = dest_id
                logger.info(f"✅ Grupo encontrado en diálogos: '{dialog.title}' (ID {dest_id})")
                try:
                    exported = await client(ExportChatInviteRequest(peer=entity, title="Enlace Cine 80 y 90"))
                    if isinstance(exported, ChatInviteExported):
                        state["dest_invite_link"] = exported.link
                except Exception:
                    pass
                save_state(state)
                return entity

    # 3. Crear grupo si no existe
    logger.info(f"🚀 Creando grupo '{TARGET_GROUP_TITLE}'...")
    created = await client(CreateChannelRequest(
        title=TARGET_GROUP_TITLE,
        about="Películas de los años 80 y 90 (1980 - 1999) en Español",
        megagroup=True
    ))
    entity = created.chats[0]
    dest_id = utils.get_peer_id(entity)
    state["dest_chat_id"] = dest_id
    try:
        exported = await client(ExportChatInviteRequest(peer=entity, title="Enlace Cine 80 y 90"))
        if isinstance(exported, ChatInviteExported):
            state["dest_invite_link"] = exported.link
    except Exception:
        pass
    save_state(state)
    logger.info(f"🎉 Grupo creado exitosamente con ID: {dest_id} | Enlace: {state.get('dest_invite_link')}")
    return entity


async def sync_peliculas_80_90():
    if not STRING_SESSION:
        logger.error("TELEGRAM_STRING_SESSION no configurada.")
        sys.exit(1)

    if os.path.exists(MORE_MARKER):
        try:
            os.remove(MORE_MARKER)
        except Exception:
            pass

    state = load_state()
    synced_titles = set(state.get("forwarded_titles", []))
    forwarded_msg_ids = set(state.get("forwarded_msg_ids", []))

    async with TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH) as client:
        logger.info("=" * 65)
        logger.info(f"SINCRONIZACIÓN - CINE DE LOS 80 Y 90 ({MIN_YEAR} - {MAX_YEAR})")
        logger.info(f"Origen: Chat {SOURCE_CHAT_ID} | Tema {SOURCE_TOPIC_ID}")
        logger.info(f"Destino: '{TARGET_GROUP_TITLE}'")
        logger.info("=" * 65)

        dest_chat = await get_or_create_target_group(client, state)
        source_chat = await client.get_entity(SOURCE_CHAT_ID)

        last_id_scanned = state.get("last_message_id_scanned", 0)
        iter_kwargs = {}
        if SOURCE_TOPIC_ID > 0:
            iter_kwargs["reply_to"] = SOURCE_TOPIC_ID
        if last_id_scanned > 0:
            iter_kwargs["max_id"] = last_id_scanned
            logger.info(f"Continuando escaneo hacia atrás desde Msg ID < {last_id_scanned}...")
        else:
            logger.info("Iniciando escaneo desde las publicaciones más recientes hacia atrás...")

        scanned_count = 0
        forwarded_in_run = 0
        current_lowest_id = last_id_scanned

        async for msg in client.iter_messages(source_chat, **iter_kwargs):
            scanned_count += 1
            current_lowest_id = msg.id

            if state.get("highest_id_scanned", 0) == 0:
                state["highest_id_scanned"] = msg.id

            if scanned_count % 100 == 0:
                logger.info(f"🔍 [Progreso escaneo] {scanned_count} mensajes analizados (Msg ID actual: {msg.id}) | Películas 80s/90s reenviadas: {forwarded_in_run}")

            # 1. Verificar formato video
            is_valid, fname = is_target_movie_video(msg)
            if not is_valid:
                continue

            caption = msg.text or getattr(msg, 'message', '') or ""
            combined_text = f"{fname} {caption}".strip()

            # 2. Extraer año y validar rango 1980 - 1999
            year = extract_movie_year(combined_text)
            if not year or not (MIN_YEAR <= year <= MAX_YEAR):
                continue

            # 3. Normalizar título para desduplicar
            norm_title = normalize_movie_title(fname, caption)
            if not norm_title or len(norm_title) < 2:
                norm_title = re.sub(r"\.[a-zA-Z0-9]+$", "", fname).strip().lower()

            unique_key = f"{norm_title}_{year}"

            # 4. Comprobar si ya fue enviada
            if unique_key in synced_titles:
                logger.info(f"⏭️ Omitida (ya sincronizada): '{norm_title}' ({year})")
                continue

            # 5. Reenvío limpio en tiempo real
            file_size_mb = get_media_size(msg) / (1024 * 1024)
            display_title = norm_title.title()
            send_caption = caption if len(caption.strip()) >= 5 else f"{display_title} ({year})"

            logger.info(f"🎬 [{forwarded_in_run + 1}/{BATCH_FORWARD_LIMIT}] Reenviando al canal: {display_title} ({year}) | {file_size_mb:.1f} MB (Msg ID: {msg.id})...")

            sent_success = False
            for attempt in range(3):
                try:
                    await client.send_message(
                        dest_chat,
                        message=send_caption,
                        file=msg.media
                    )
                    sent_success = True
                    break
                except errors.FloodWaitError as fwe:
                    wait_s = fwe.seconds + 5
                    logger.warning(f"FloodWait de Telegram detectado: pausando {wait_s} segundos...")
                    await asyncio.sleep(wait_s)
                except Exception as e:
                    logger.warning(f"Aviso send_message ({e}), intentando forward_messages...")
                    try:
                        await client.forward_messages(dest_chat, msg)
                        sent_success = True
                        break
                    except errors.FloodWaitError as fwe:
                        wait_s = fwe.seconds + 5
                        logger.warning(f"FloodWait detectado: pausando {wait_s} segundos...")
                        await asyncio.sleep(wait_s)
                    except Exception as e2:
                        logger.error(f"Error reenviando película '{unique_key}': {e2}")
                        await asyncio.sleep(3)

            if sent_success:
                forwarded_in_run += 1
                synced_titles.add(unique_key)
                state["forwarded_titles"].append(unique_key)
                state["forwarded_msg_ids"].append(msg.id)
                state["total_synced"] = len(synced_titles)
                state["last_message_id_scanned"] = msg.id
                save_state(state)
                logger.info(f"✅ ¡Película enviada con éxito!: '{display_title}' ({year})")

                # Pausa preventiva entre envíos
                await asyncio.sleep(random.uniform(2.5, 3.8))

            if forwarded_in_run >= BATCH_FORWARD_LIMIT:
                logger.info(f"🎯 Límite de lote alcanzado ({BATCH_FORWARD_LIMIT} películas reenviadas).")
                break

            if scanned_count >= MAX_MESSAGES_TO_SCAN:
                logger.info(f"Escaneados {scanned_count} mensajes en este ciclo.")
                break

        if current_lowest_id and current_lowest_id > 0:
            state["last_message_id_scanned"] = current_lowest_id
        save_state(state)

        logger.info("=" * 65)
        logger.info(f"RESUMEN DE LA TANDA:")
        logger.info(f"  • Mensajes escaneados: {scanned_count}")
        logger.info(f"  • Películas 80s/90s reenviadas en esta tanda: {forwarded_in_run}")
        logger.info(f"  • Total acumulado en '{TARGET_GROUP_TITLE}': {state['total_synced']}")
        logger.info(f"  • Último Msg ID escaneado: {state['last_message_id_scanned']}")
        logger.info("=" * 65)

        # Si aún quedan mensajes históricos por recorrer hacia atrás (> 1)
        if current_lowest_id and current_lowest_id > 1:
            logger.info(f"Aún queda catálogo pendiente. Creando marcador '{MORE_MARKER}'...")
            with open(MORE_MARKER, "w") as f:
                f.write(str(current_lowest_id))
        else:
            logger.info("🎉 ¡Se ha explorado la totalidad del catálogo del origen!")


if __name__ == "__main__":
    asyncio.run(sync_peliculas_80_90())
