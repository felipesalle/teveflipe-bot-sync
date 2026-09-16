import asyncio
import json
import logging
import os
import random
import re
import sys
import unicodedata
from collections import defaultdict
from typing import Optional, Dict, List, Tuple

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
logger = logging.getLogger("SyncPeliculasClasicas")

# Credenciales
API_ID = int(os.getenv("TELEGRAM_API_ID") or 0)
API_HASH = os.getenv("TELEGRAM_API_HASH") or ""
STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION") or ""

# Canal y Tema Origen (https://web.telegram.org/a/#-1001905652210_7)
SOURCE_CHAT_ID = int(os.getenv("CLASICAS_SOURCE_CHAT", "-1001905652210"))
SOURCE_TOPIC_ID = int(os.getenv("CLASICAS_SOURCE_TOPIC", "7"))

TARGET_GROUP_TITLE = "Peliculas Clasicas"
STATE_FILE = "sync_state_clasicas.json"
MORE_MARKER = ".more_clasicas"
BATCH_FORWARD_LIMIT = int(os.getenv("BATCH_FORWARD_LIMIT", "100"))
CUTOFF_YEAR = 1955  # Exclusivo: solo películas < 1955 (hasta 1954 inclusive)


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Error cargando {STATE_FILE}: {e}")
    return {
        "dest_chat_id": None,
        "dest_invite_link": "",
        "forwarded_titles": [],
        "forwarded_msg_ids": [],
        "total_synced": 0,
        "last_message_id_scanned": 0
    }


def save_state(state: dict):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error guardando {STATE_FILE}: {e}")


def extract_movie_year(raw_text: str) -> Optional[int]:
    """
    Extrae el año de producción a partir del título, ficha o nombre de archivo.
    """
    if not raw_text:
        return None

    text = raw_text

    # 1. Metadatos explícitos (ej: "Año: 1942", "Estreno: 1939", "Year: 1950")
    explicit_match = re.search(r'(?i)\b(?:a[ñn]o|year|estreno|fecha|lan[zç]amiento)[:\s]+(\d{4})\b', text)
    if explicit_match:
        y = int(explicit_match.group(1))
        if 1888 <= y <= 2030:
            return y

    # 2. Limpiar resoluciones y códecs que puedan confundir al buscador
    cleaned = re.sub(r'(?i)\b(?:1080p?|1080i|720p?|2160p?|480p?|576p?|x264|x265|h264|h265|5\.1|7\.1)\b', ' ', text)

    # 3. Año entre paréntesis o corchetes: (1942), [1939]
    bracket_match = re.search(r'[\(\[]\s*(\b1[89]\d{2}|20\d{2}\b)\s*[\)\]]', cleaned)
    if bracket_match:
        y = int(bracket_match.group(1))
        if 1888 <= y <= 2030:
            return y

    # 4. Delimitado por guiones, puntos o espacios: .1942., _1939_, - 1950 -
    delimiters_match = re.search(r'(?:[._\-\s])(1[89]\d{2}|20\d{2})(?:[._\-\s]|$)', cleaned)
    if delimiters_match:
        y = int(delimiters_match.group(1))
        if 1888 <= y <= 2030:
            return y

    # 5. 4 dígitos aislados
    general_match = re.search(r'\b(1[89]\d{2}|20\d{2})\b', cleaned)
    if general_match:
        y = int(general_match.group(1))
        if 1888 <= y <= 2030:
            return y

    return None


def normalize_movie_title(raw_title: str, caption: str = "") -> str:
    """
    Genera una clave normalizada de película (sin año ni etiquetas técnicas) para desduplicar.
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

    # 1. Quitar extensiones
    text = re.sub(r"\.[a-zA-Z0-9]{2,4}$", "", cand)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[@#]\w+", "", text)

    # 2. Descomponer y eliminar acentos
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))

    # 3. Quitar emojis
    text = re.sub(r"[\U00010000-\U0010ffff]", "", text)
    text = re.sub(r"[\u2600-\u27bf\u2300-\u23ff\u2b50\u2b55\ufe0f]", "", text)

    # 4. Aislar título si viene con paréntesis
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
    Verifica si el mensaje es un video en formato .mkv o .mp4.
    Retorna (es_valido, nombre_archivo).
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
    has_target_ext = fname_lower.endswith((".mkv", ".mp4"))

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

    if (is_video or has_target_ext) and has_target_ext:
        return True, fname

    return False, fname


def get_media_size(message) -> int:
    if getattr(message, "file", None) and hasattr(message.file, "size"):
        return message.file.size or 0
    if message.media and isinstance(message.media, MessageMediaDocument) and message.media.document:
        return getattr(message.media.document, "size", 0) or 0
    return 0


async def get_or_create_clasicas_group(client: TelegramClient, state: dict):
    """
    Busca si ya existe el grupo privado 'Peliculas Clasicas' en la cuenta o en el estado.
    Si no existe, lo crea como megagrupo privado y genera un enlace de invitación.
    """
    # 1. Intentar resolver el grupo guardado en el archivo de estado
    saved_chat_id = state.get("dest_chat_id")
    if saved_chat_id:
        try:
            entity = await client.get_entity(saved_chat_id)
            logger.info(f"✅ Grupo destino verificado desde estado: '{getattr(entity, 'title', '')}' (ID {saved_chat_id})")
            return entity
        except Exception as e:
            logger.warning(f"No se pudo cargar grupo por ID guardado ({saved_chat_id}): {e}")

    # 2. Buscar en los diálogos del usuario
    logger.info("Buscando grupo 'Peliculas Clasicas' en los diálogos del usuario...")
    async for dialog in client.iter_dialogs(limit=150):
        if (dialog.is_channel or dialog.is_group) and dialog.title:
            if dialog.title.strip().lower() == TARGET_GROUP_TITLE.strip().lower():
                entity = dialog.entity
                dest_id = utils.get_peer_id(entity)
                state["dest_chat_id"] = dest_id
                logger.info(f"✅ Grupo existente encontrado en diálogos: '{dialog.title}' (ID {dest_id})")
                save_state(state)
                return entity

    # 3. Si no existe, crear el Grupo Privado (megagrupo)
    logger.info(f"🚀 Creando nuevo Grupo Privado: '{TARGET_GROUP_TITLE}'...")
    created = await client(CreateChannelRequest(
        title=TARGET_GROUP_TITLE,
        about="Películas Clásicas de la Época Dorada (< 1955)",
        megagroup=True
    ))
    entity = created.chats[0]
    dest_id = utils.get_peer_id(entity)
    state["dest_chat_id"] = dest_id
    logger.info(f"✅ Grupo creado exitosamente con ID {dest_id}!")

    # Generar enlace de invitación
    try:
        exported = await client(ExportChatInviteRequest(peer=entity, title="Enlace Películas Clásicas"))
        if isinstance(exported, ChatInviteExported):
            state["dest_invite_link"] = exported.link
            logger.info(f"🔗 Enlace de invitación privado: {exported.link}")
    except Exception as e:
        logger.warning(f"No se pudo exportar enlace de invitación: {e}")

    save_state(state)
    return entity


async def sync_peliculas_clasicas():
    if not STRING_SESSION:
        logger.error("TELEGRAM_STRING_SESSION no configurada en las variables de entorno.")
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
        logger.info("SINCRONIZACIÓN DE PELÍCULAS CLÁSICAS (< 1955)")
        logger.info(f"Origen: Chat {SOURCE_CHAT_ID} | Tema {SOURCE_TOPIC_ID}")
        logger.info("=" * 65)

        # 1. Obtener o crear grupo destino
        dest_chat = await get_or_create_clasicas_group(client, state)
        dest_id = utils.get_peer_id(dest_chat)

        # 2. Resolver canal de origen
        source_chat = None
        async for dialog in client.iter_dialogs(limit=100):
            if dialog.id == SOURCE_CHAT_ID or str(SOURCE_CHAT_ID) in str(dialog.id):
                source_chat = dialog.entity
                logger.info(f"Canal origen encontrado en diálogos: '{dialog.title}' (ID {dialog.id})")
                break
        if not source_chat:
            source_chat = await client.get_entity(SOURCE_CHAT_ID)

        # 3. Escaneo del tema origen
        logger.info(f"Escaneando mensajes del tema {SOURCE_TOPIC_ID} en {getattr(source_chat, 'title', SOURCE_CHAT_ID)}...")
        raw_video_count = 0
        candidates = defaultdict(list)
        skipped_no_year = 0
        skipped_newer = 0

        async for msg in client.iter_messages(source_chat, reply_to=SOURCE_TOPIC_ID, reverse=True):
            is_valid, fname = is_target_movie_video(msg)
            if not is_valid:
                continue

            raw_video_count += 1
            caption = msg.text or ""
            combined_text = f"{fname} {caption}"

            year = extract_movie_year(combined_text)
            if year is None:
                skipped_no_year += 1
                continue

            if year >= CUTOFF_YEAR:
                skipped_newer += 1
                continue

            # Es película clásica anterior a 1955 (< 1955)
            norm_title = normalize_movie_title(fname, caption)
            if not norm_title or len(norm_title) < 2:
                norm_title = re.sub(r"\.[a-zA-Z0-9]+$", "", fname).strip().lower()

            unique_key = f"{norm_title}_{year}"
            candidates[unique_key].append(msg)

        logger.info("--- RESUMEN DEL ESCANEO ---")
        logger.info(f"Total videos .mkv / .mp4 analizados: {raw_video_count}")
        logger.info(f"Omitidos por ser del año >= 1955: {skipped_newer}")
        logger.info(f"Omitidos sin año detectable en título/ficha: {skipped_no_year}")
        logger.info(f"Películas clásicas únicas detectadas (< 1955): {len(candidates)}")

        # 4. Desduplicación y filtrado contra estado previo
        movies_to_forward = []
        for key, msgs in candidates.items():
            if key in synced_titles:
                continue

            # Seleccionar la mejor versión (mayor tamaño de archivo / mejor calidad)
            best_msg = max(msgs, key=lambda m: get_media_size(m))
            movies_to_forward.append((key, best_msg, msgs))

        logger.info(f"Películas pendientes de sincronizar: {len(movies_to_forward)}")
        if not movies_to_forward:
            logger.info("✅ No hay películas clásicas nuevas pendientes de sincronizar.")
            return

        # 5. Aplicar límite de lote para este run
        batch = movies_to_forward[:BATCH_FORWARD_LIMIT]
        remaining = len(movies_to_forward) - len(batch)
        logger.info(f"Procesando lote de {len(batch)} películas en esta ejecución (Quedarán {remaining} para el siguiente ciclo)...")

        forwarded_in_run = 0
        for idx, (key, best_msg, all_msgs) in enumerate(batch, 1):
            is_valid, fname = is_target_movie_video(best_msg)
            file_size_mb = get_media_size(best_msg) / (1024 * 1024)
            caption = best_msg.text or fname or key.replace("_", " ").title()

            logger.info(f"[{idx}/{len(batch)}] Sincronizando: {fname or key} ({file_size_mb:.1f} MB)...")
            
            sent_success = False
            for attempt in range(3):
                try:
                    # Intento 1: Envío directo del archivo multimedia (copia nativa limpia en Telegram)
                    await client.send_message(
                        dest_chat,
                        message=caption,
                        file=best_msg.media
                    )
                    sent_success = True
                    break
                except errors.FloodWaitError as fwe:
                    wait_s = fwe.seconds + 5
                    logger.warning(f"FloodWait detectado: pausando {wait_s} segundos...")
                    await asyncio.sleep(wait_s)
                except Exception as e:
                    logger.warning(f"Aviso en send_message ({e}), intentando forward_messages...")
                    try:
                        await client.forward_messages(dest_chat, best_msg)
                        sent_success = True
                        break
                    except errors.FloodWaitError as fwe:
                        wait_s = fwe.seconds + 5
                        logger.warning(f"FloodWait detectado: pausando {wait_s} segundos...")
                        await asyncio.sleep(wait_s)
                    except Exception as e2:
                        logger.error(f"Error reenviando película '{key}': {e2}")
                        await asyncio.sleep(3)

            if sent_success:
                forwarded_in_run += 1
                synced_titles.add(key)
                state["forwarded_titles"].append(key)
                for m in all_msgs:
                    forwarded_msg_ids.add(m.id)
                    state["forwarded_msg_ids"].append(m.id)
                state["total_synced"] = len(synced_titles)
                save_state(state)
                # Pausa de cortesía para no saturar Telegram
                await asyncio.sleep(random.uniform(2.5, 4.0))

        logger.info(f"✅ Lote finalizado: {forwarded_in_run} películas clásicas enviadas al grupo '{TARGET_GROUP_TITLE}'.")
        
        if remaining > 0:
            logger.info(f"Quedan {remaining} películas pendientes. Creando marcador '{MORE_MARKER}'...")
            with open(MORE_MARKER, "w") as f:
                f.write(str(remaining))


if __name__ == "__main__":
    asyncio.run(sync_peliculas_clasicas())
