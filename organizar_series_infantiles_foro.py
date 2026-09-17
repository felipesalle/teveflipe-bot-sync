import asyncio
import json
import logging
import os
import random
import re
from collections import defaultdict
from telethon import TelegramClient, errors, utils
from telethon.sessions import StringSession
from telethon.tl.functions.channels import CreateChannelRequest, ToggleForumRequest
from telethon.tl.functions.messages import (
    CreateForumTopicRequest,
    ExportChatInviteRequest,
    ForwardMessagesRequest,
    GetForumTopicsRequest
)
from telethon.tl.types import (
    ChatInviteExported,
    DocumentAttributeFilename,
    DocumentAttributeVideo,
    MessageMediaDocument
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("ForoSeriesInfantiles")

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION", "")

SOURCE_CHANNEL_ID = int(os.getenv("CANAL_SERIES_ID", "-1003874872975"))
STATE_FILE = "foro_infantil_state.json"
INDEX_FILE = "index_episodios_infantiles.json"

CLEAN_TAGS_REGEX = re.compile(
    r"(?i)\b(1080p|720p|480p|4k|2160p|bluray|bdrip|web-?dl|webrip|dvdrip|hdtv|tvrip|x264|x265|hevc|h264|h265|aac|ac3|dts|dual|latino|castellano|espanol|spanish|subtitulado|sub|subs|vose|hd|rip|xvid|divx|flv|mp4|mkv|avi|microhd|completa|audio)\b"
)

SERIES_SEASON_EP_REGEX = re.compile(
    r"(?i)(?:[sS](\d{1,2})[eE](\d{1,3})|(\d{1,2})x(\d{1,3})|\b(?:cap[íi]tulo|cap|episodio|ep)\s*(\d{1,3})\b|\bT(\d{1,2})\b|\b(?:temp|temporada)\s*(\d{1,2})\b)",
    re.IGNORECASE
)

TRAILING_NUM_REGEX = re.compile(r"[-–—_]\s*(\d{1,3})\s*$", re.IGNORECASE)


def extract_filename(msg) -> str:
    if getattr(msg, "file", None) and getattr(msg.file, "name", None):
        return msg.file.name or ""
    if msg.media and isinstance(msg.media, MessageMediaDocument) and msg.media.document:
        for attr in msg.media.document.attributes:
            if isinstance(attr, DocumentAttributeFilename):
                return attr.file_name or ""
    return ""


def clean_series_name(raw_name: str, caption: str = "") -> str:
    cand = raw_name
    if not cand and caption:
        cand = caption.split("\n")[0].strip()
    if not cand:
        return ""

    # Quitar extensiones
    name = re.sub(r"\.[a-zA-Z0-9]{2,4}$", "", cand)
    name = name.replace(".", " ").replace("_", " ")

    m = SERIES_SEASON_EP_REGEX.search(name)
    if m:
        if m.start() == 0:
            name = name[m.end():].strip()
        else:
            name = name[:m.start()].strip()
    else:
        tm = TRAILING_NUM_REGEX.search(name)
        if tm:
            name = name[:tm.start()].strip()

    name = re.sub(r"\b(19\d\d|20\d\d)\b", "", name)
    name = CLEAN_TAGS_REGEX.sub("", name)
    name = re.sub(r"[\[\]\(\)\{\}\-–—+!¡?¿*#|│]+", " ", name)
    clean_title = re.sub(r"\s+", " ", name).strip()

    if clean_title:
        words = clean_title.split()
        clean_title = " ".join(w.capitalize() if not w.isupper() else w for w in words)
        return clean_title
    return ""


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Error leyendo {STATE_FILE}: {e}")
    return {
        "supergroup_id": 0,
        "supergroup_link": "",
        "topics_cache": {},
        "completed_series": [],
        "total_forwarded": 0
    }


def save_state(state: dict):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error guardando {STATE_FILE}: {e}")


async def get_or_create_forum_group(client: TelegramClient, state: dict):
    group_id = state.get("supergroup_id", 0)
    if group_id != 0:
        try:
            entity = await client.get_entity(group_id)
            logger.info(f"Supergrupo foro recuperado del estado: {entity.title} (ID: {group_id})")
            return entity, group_id, state.get("supergroup_link", "")
        except Exception as e:
            logger.warning(f"No se pudo cargar grupo por ID {group_id}: {e}")

    # Buscar en dialogos existentes
    logger.info("Buscando si ya existe un grupo 'Series Infantiles' en la cuenta...")
    async for dialog in client.iter_dialogs(limit=100):
        if dialog.is_group and "Series Infantiles" in dialog.title:
            entity = dialog.entity
            g_id = utils.get_peer_id(entity)
            logger.info(f"Supergrupo existente encontrado: {dialog.title} (ID: {g_id})")
            state["supergroup_id"] = g_id
            save_state(state)
            return entity, g_id, state.get("supergroup_link", "")

    # Crear supergrupo con foro habilitado
    logger.info("Creando nuevo Supergrupo Foro en Telegram...")
    created = await client(CreateChannelRequest(
        title="Series Infantiles",
        about="Series infantiles y dibujos animados organizados por temas para TeveFlipe Android TV.",
        broadcast=False,
        megagroup=True,
        forum=True
    ))
    group = created.chats[0]
    g_id = utils.get_peer_id(group)
    logger.info(f"Supergrupo creado con éxito: ID {g_id}")

    try:
        await client(ToggleForumRequest(channel=group, enabled=True, tabs=False))
        logger.info("Foros/Temas habilitados.")
    except Exception as e:
        logger.warning(f"Aviso activando foro: {e}")

    invite_link = ""
    try:
        exported = await client(ExportChatInviteRequest(peer=group, title="Enlace TeveFlipe Series"))
        if isinstance(exported, ChatInviteExported):
            invite_link = exported.link
            logger.info(f"Enlace de invitación generado: {invite_link}")
    except Exception as e:
        logger.warning(f"Aviso enlace invitacion: {e}")

    state["supergroup_id"] = g_id
    state["supergroup_link"] = invite_link
    save_state(state)
    return group, g_id, invite_link


async def get_or_create_topic(client: TelegramClient, group_entity, series_name: str, state: dict) -> int:
    norm_key = series_name.strip().lower()
    topics_cache = state.setdefault("topics_cache", {})

    if norm_key in topics_cache:
        return topics_cache[norm_key]

    try:
        colors = [0x6FB9F0, 0xFFD67E, 0xCB86DB, 0x8EEE98, 0xFF93B2, 0xFB6F5F]
        rand_id = random.randint(1, 2**63 - 1)
        created = await client(CreateForumTopicRequest(
            peer=group_entity,
            title=series_name[:128],
            icon_color=random.choice(colors),
            random_id=rand_id
        ))

        topic_id = None
        for update in getattr(created, "updates", []):
            msg = getattr(update, "message", None)
            if msg and hasattr(msg, "id"):
                topic_id = msg.id
                break
            elif hasattr(update, "id"):
                topic_id = update.id

        if topic_id:
            logger.info(f"✅ Tema creado en foro: '{series_name}' (Topic ID: {topic_id})")
            topics_cache[norm_key] = topic_id
            save_state(state)
            return topic_id
    except errors.FloodWaitError as e:
        logger.warning(f"FloodWait creando tema: esperando {e.seconds + 1}s...")
        await asyncio.sleep(e.seconds + 1)
        return await get_or_create_topic(client, group_entity, series_name, state)
    except Exception as e:
        logger.error(f"Error creando tema para '{series_name}': {e}")

    return None


async def index_episodes(client: TelegramClient, source_channel) -> dict:
    if os.path.exists(INDEX_FILE):
        try:
            logger.info(f"Cargando índice previo de episodios desde {INDEX_FILE}...")
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if len(data) > 0:
                    logger.info(f"Índice cargado con éxito ({len(data)} series).")
                    return data
        except Exception as e:
            logger.warning(f"Error leyendo {INDEX_FILE}: {e}")

    logger.info("Indexando episodios del canal privado de Series Infantiles...")
    series_map = defaultdict(list)
    total_msgs = 0

    async for msg in client.iter_messages(source_channel, limit=None):
        if not msg or not msg.media:
            continue
        total_msgs += 1
        fname = extract_filename(msg)
        caption = msg.raw_text or ""
        series_title = clean_series_name(fname, caption)

        if not series_title or len(series_title) < 2 or series_title.lower() == "sin título":
            continue

        series_map[series_title].append(msg.id)

        if total_msgs % 3000 == 0:
            logger.info(f"Indexados {total_msgs} mensajes... ({len(series_map)} series)")

    # Ordenar los IDs de mensajes de cada serie en orden cronológico ascendente (para que el capítulo 1 quede arriba)
    sorted_map = {}
    for s_title, m_ids in series_map.items():
        sorted_map[s_title] = sorted(m_ids)

    logger.info(f"Indexación completada. Total series identificadas: {len(sorted_map)}")
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted_map, f, indent=2, ensure_ascii=False)
    logger.info(f"Índice guardado en {INDEX_FILE}")

    return sorted_map


async def run_organizer():
    if not STRING_SESSION:
        logger.error("TELEGRAM_STRING_SESSION no configurada.")
        return

    state = load_state()
    logger.info("=" * 65)
    logger.info("ORGANIZADOR DE SERIES INFANTILES EN SUPERGRUPO FORO")
    logger.info(f"Canal Origen: {SOURCE_CHANNEL_ID}")
    logger.info(f"Series completadas previamente: {len(state.get('completed_series', []))}")
    logger.info("=" * 65)

    async with TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH) as client:
        source_channel = await client.get_entity(SOURCE_CHANNEL_ID)
        dest_group, dest_id, invite_link = await get_or_create_forum_group(client, state)

        series_index = await index_episodes(client, source_channel)

        # Filtrar series con al menos 3 episodios y ordenarlas por cantidad de episodios (mayores primero)
        eligible_series = [
            (title, ids) for title, ids in series_index.items()
            if len(ids) >= 3
        ]
        eligible_series.sort(key=lambda x: len(x[1]), reverse=True)

        logger.info(f"Total series elegibles para temas (>= 3 capítulos): {len(eligible_series)}")

        completed_set = set(state.get("completed_series", []))
        total_forwarded = state.get("total_forwarded", 0)

        for idx, (series_title, msg_ids) in enumerate(eligible_series, start=1):
            if series_title in completed_set:
                continue

            logger.info(f"\n[{idx}/{len(eligible_series)}] Procesando serie: '{series_title}' ({len(msg_ids)} episodios)...")

            topic_id = await get_or_create_topic(client, dest_group, series_title, state)
            if not topic_id:
                logger.warning(f"No se pudo obtener tema para '{series_title}'. Omitiendo temporalmente.")
                continue

            # Reenviar en bloques de 45 episodios
            chunk_size = 45
            for i in range(0, len(msg_ids), chunk_size):
                chunk = msg_ids[i:i + chunk_size]
                rand_ids = [random.randint(1, 2**63 - 1) for _ in chunk]

                success = False
                for attempt in range(4):
                    try:
                        await client(ForwardMessagesRequest(
                            from_peer=source_channel,
                            to_peer=dest_group,
                            id=chunk,
                            random_id=rand_ids,
                            top_msg_id=topic_id,
                            drop_author=True
                        ))
                        total_forwarded += len(chunk)
                        state["total_forwarded"] = total_forwarded
                        success = True
                        break
                    except errors.FloodWaitError as e:
                        logger.warning(f"FloodWait de {e.seconds}s. Esperando...")
                        await asyncio.sleep(e.seconds + 1)
                    except Exception as e:
                        logger.warning(f"Error reenviando bloque (intento {attempt + 1}): {e}")
                        await asyncio.sleep(3)

                if success:
                    await asyncio.sleep(1.8)

            completed_set.add(series_title)
            state["completed_series"] = list(completed_set)
            save_state(state)
            logger.info(f"✅ Serie '{series_title}' transferida completamente al tema {topic_id} ({len(msg_ids)} eps). Total transferidos: {total_forwarded}")

        logger.info("\n" + "=" * 65)
        logger.info("¡ORGANIZACIÓN DE SERIES EN FORO COMPLETADA CON ÉXITO!")
        logger.info(f"Supergrupo ID: {dest_id}")
        logger.info(f"Enlace de invitación: {invite_link}")
        logger.info(f"Total Series con Tema: {len(completed_set)}")
        logger.info(f"Total Episodios Transferidos: {total_forwarded}")
        logger.info("=" * 65)


if __name__ == "__main__":
    asyncio.run(run_organizer())
