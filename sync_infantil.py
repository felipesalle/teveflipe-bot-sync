import os
import json
import asyncio
import re
import random
import logging
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.functions.channels import (
    CreateChannelRequest,
    ToggleForumRequest
)
from telethon.tl.functions.messages import (
    ForwardMessagesRequest,
    GetForumTopicsRequest,
    CreateForumTopicRequest,
    ExportChatInviteRequest
)
from telethon.tl.types import (
    MessageMediaDocument,
    DocumentAttributeVideo,
    DocumentAttributeFilename,
    Channel,
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
BATCH_SIZE = 50  # Lote de reenvío por bloques
VIDEO_EXTENSIONS = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.m4v', '.webm', '.ts')


def es_archivo_video(msg) -> bool:
    """Filtra y descarta archivos que no sean vídeo (.mp4, .mkv, etc.)."""
    if not msg or not msg.media:
        return False
    if getattr(msg, "video", None):
        return True
    if isinstance(msg.media, MessageMediaDocument):
        doc = msg.media.document
        if doc:
            mime = (doc.mime_type or "").lower()
            if mime.startswith("video/"):
                return True
            for attr in doc.attributes:
                if isinstance(attr, (DocumentAttributeVideo,)):
                    return True
                if isinstance(attr, DocumentAttributeFilename):
                    fname = (attr.file_name or "").lower()
                    if fname.endswith(VIDEO_EXTENSIONS):
                        return True
    return False


def extract_file_name(msg) -> str:
    if getattr(msg, "file", None) and getattr(msg.file, "name", None):
        return msg.file.name or ""
    if msg.media and isinstance(msg.media, MessageMediaDocument) and msg.media.document:
        for attr in msg.media.document.attributes:
            if isinstance(attr, DocumentAttributeFilename):
                return attr.file_name or ""
    return ""


def clean_series_name(text: str) -> str:
    """Extrae un nombre limpio de serie descartando códigos de episodio y coletillas."""
    if not text:
        return "Serie Infantil"
    
    t = text.strip().split("\n")[0].strip()
    t = re.sub(r"\.[a-zA-Z0-9]{2,4}$", "", t)
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"[@#]\w+", "", t)
    t = re.sub(r"\[.*?\]|\(.*?\)", "", t)
    t = re.sub(r"[\U00010000-\U0010ffff]", "", t)
    t = t.replace("_", " ").replace(".", " ")

    # Si empieza con números de capítulo (ej. "01 - Titulo", "1x01 Titulo")
    t = re.sub(r"^\s*(?:\d{1,3}\s*[-–—.:]\s*|\d+[xX×\u00d7]\d+\s*[-–—.:]?\s*|[sS]\d+(?:[eE]\d+)?\s*[-–—.:]?\s*|cap[ií]tulo\s*\d+\s*[-–—.:]?\s*)", "", t, flags=re.I)

    # Cortar en patrones de temporada/episodio o numeración de capítulo
    parts = re.split(
        r"(?i)\b(?:S\d+(?:E\d+)?|T\d+(?:E\d+)?|Temporada\s*\d+|\d+[xX×\u00d7]\d+|Cap(?:[iíãÃ\ufffd\xad\s]*tulo|\.)?\s*\d+|Ep(?:isodio|\.)?\s*\d+|Parte\s*\d+|\s*[-–—_]\s*\d{1,3}\b)\b",
        t
    )
    cand = parts[0].strip() if parts else t

    # Quitar resoluciones, códecs e idiomas
    cand = re.sub(r"(?i)\b(?:1080p?|720p?|4k|web-?dl|webrip|bluray|dvdrip|hdtv|x264|x265|hevc|latino|castellano|español|dual|multi|subs?)\b", " ", cand)
    cand = re.sub(r"^[-–—:\s*=#~▶►]+|[-–—:\s*=#~▶►]+$", "", cand).strip()
    cand = re.sub(r"\s+", " ", cand).strip()

    if len(cand) >= 2 and any(c.isalpha() for c in cand):
        return cand.title()
    return "Serie Infantil"


def clasificar_contenido(msg) -> tuple:
    """
    Retorna ('SERIE', nombre_serie) o ('PELICULA', None) usando la regla híbrida:
    1. Patrones de texto en el nombre del archivo o mensaje.
    2. Duración del vídeo en segundos.
    """
    fname = extract_file_name(msg)
    texto = (msg.text or "") + " " + fname
    
    duracion_segundos = 0
    if getattr(msg, "video", None) and getattr(msg.video, "duration", None):
        duracion_segundos = msg.video.duration
    elif msg.media and isinstance(msg.media, MessageMediaDocument) and msg.media.document:
        for attr in msg.media.document.attributes:
            if hasattr(attr, "duration") and attr.duration:
                duracion_segundos = attr.duration
                break

    minutos = duracion_segundos / 60.0

    # 1. Detección por patrones explícitos de series (códigos o guiones con número de capítulo)
    patron_serie = re.search(
        r"(?i)(?:s\d+|temporada|temp\b|cap[íi]tulo|cap\b|\d+[xX×\u00d7]\d+|ep\b|episodio|\b[-–—_]\s*\d{1,3}\b|\b\d{1,3}\s*[-–—_]|\bepisodios?\b)",
        texto
    )
    if patron_serie:
        return "SERIE", clean_series_name(fname or msg.text or "")

    # 2. Detección por duración en contenido infantil
    if duracion_segundos > 0:
        if minutos < 45.0:
            return "SERIE", clean_series_name(fname or msg.text or "")
        elif minutos >= 50.0:
            return "PELICULA", None

    # 3. Fallback SOLO si dice explícitamente película/movie/film (NUNCA por 1080p o dvdrip)
    if re.search(r"(?i)\b(?:pelicula|película|movie|film|largometraje)\b", texto):
        return "PELICULA", None

    # Si tiene números típicos de capítulos (ej. "Fraggle Rock 01", "Doraemon 12")
    if re.search(r"\b\d{1,3}\b", fname):
        return "SERIE", clean_series_name(fname or msg.text or "")

    if duracion_segundos > 0 and minutos >= 50.0:
        return "PELICULA", None

    return "SERIE", clean_series_name(fname or msg.text or "")


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
        "series_topics_cache": {},
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


async def forward_batch(client: TelegramClient, source_chat, dest_chat, msg_ids: list, topic_id=None, tipo=""):
    """Reenvía un lote de mensajes usando ForwardMessagesRequest con soporte para top_msg_id (temas)."""
    if not msg_ids:
        return

    source_input = await client.get_input_entity(source_chat)
    dest_input = await client.get_input_entity(dest_chat)

    enviado = False
    while not enviado:
        try:
            req = ForwardMessagesRequest(
                from_peer=source_input,
                id=msg_ids,
                to_peer=dest_input,
                random_id=[random.randint(1, 2**63 - 1) for _ in msg_ids],
                top_msg_id=topic_id,
                drop_author=True
            )
            await client(req)
            tema_info = f" -> Tema ID {topic_id}" if topic_id else ""
            logger.info(f"🚀 Lote enviado: {len(msg_ids)} {tipo} transferidos con éxito{tema_info}.")
            await asyncio.sleep(4.0)
            enviado = True
        except errors.FloodWaitError as e:
            logger.warning(f"⚠️ Telegram FloodWait: pausando {e.seconds}s de seguridad...")
            await asyncio.sleep(e.seconds + 2)
        except errors.ChatForwardsRestrictedError:
            logger.warning("Origen con restricción de reenvío. Clonando archivos multimedia directamente...")
            msgs = await client.get_messages(source_input, ids=msg_ids)
            for m in msgs:
                if m and m.media:
                    caption = m.text or (m.file.name if getattr(m, 'file', None) else "")
                    await client.send_message(dest_input, message=caption, file=m.media, reply_to=topic_id)
                    await asyncio.sleep(1.2)
            enviado = True
        except Exception as e:
            logger.error(f"❌ Error enviando lote a {tipo}: {e}")
            await asyncio.sleep(4.0)
            enviado = True


async def get_or_create_series_topic(client: TelegramClient, dest_chat, series_name: str, cache: dict) -> int:
    """Busca o crea un tema para la serie en el supergrupo de Series Infantiles."""
    norm_name = series_name.strip().lower()
    if norm_name in cache:
        return cache[norm_name]

    dest_input = await client.get_input_entity(dest_chat)

    # 1. Comprobar si ya existe en Telegram
    try:
        topics_res = await client(GetForumTopicsRequest(
            peer=dest_input,
            offset_date=None,
            offset_id=0,
            offset_topic=0,
            limit=100
        ))
        for t in getattr(topics_res, "topics", []):
            t_title = getattr(t, "title", "").strip().lower()
            t_id = getattr(t, "id", None)
            if t_title and t_id:
                cache[t_title] = t_id
                if t_title == norm_name:
                    return t_id
    except Exception as e:
        logger.warning(f"Error consultando temas existentes: {e}")

    if norm_name in cache:
        return cache[norm_name]

    # 2. Crear tema para la serie
    logger.info(f"🆕 Creando nuevo Tema en Series Infantiles: '{series_name}'...")
    while True:
        try:
            rand_id = random.randint(1, 2**63 - 1)
            created = await client(CreateForumTopicRequest(
                peer=dest_input,
                title=series_name[:128],
                random_id=rand_id
            ))
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
                logger.info(f"✅ Tema creado: '{series_name}' (Topic ID: {topic_id})")
                cache[norm_name] = topic_id
                return topic_id
        except errors.FloodWaitError as e:
            logger.warning(f"FloodWait creando tema '{series_name}': esperando {e.seconds}s...")
            await asyncio.sleep(e.seconds + 2)
        except Exception as e:
            logger.error(f"Error creando tema '{series_name}': {e}")
            await asyncio.sleep(2)
            break

    return 1  # Fallback a General


async def rescatar_series_de_pelis(client: TelegramClient, ent_pelis, ent_series, topics_cache: dict, progreso: dict):
    """Escanea el canal de Películas Infantiles para mover cualquier serie que se haya colado erróneamente (como Fraggle Rock)."""
    logger.info("🔍 Comprobando si hay series coladas en Películas Infantiles para rescatarlas...")
    dest_pelis = await client.get_input_entity(ent_pelis)
    dest_series = await client.get_input_entity(ent_series)

    rescatados = 0
    try:
        async for msg in client.iter_messages(dest_pelis, limit=350):
            if not es_archivo_video(msg):
                continue
            tipo, s_name = clasificar_contenido(msg)
            # Detección explícita de Fraggle Rock u otras series
            fname = extract_file_name(msg)
            is_fraggle = "fraggle" in (fname + (msg.text or "")).lower()
            if tipo == "SERIE" or is_fraggle:
                serie_dest = "Fraggle Rock" if is_fraggle else (s_name or "Serie Infantil")
                topic_id = await get_or_create_series_topic(client, ent_series, serie_dest, topics_cache)
                caption = msg.text or (msg.file.name if getattr(msg, "file", None) else "")
                try:
                    # Enviar al tema correspondiente en Series Infantiles
                    await client.send_message(
                        dest_series,
                        message=caption,
                        file=msg.media,
                        reply_to=topic_id
                    )
                    # Eliminar de Películas Infantiles
                    await client.delete_messages(dest_pelis, [msg.id])
                    rescatados += 1
                    progreso["series_count"] = progreso.get("series_count", 0) + 1
                    progreso["pelis_count"] = max(0, progreso.get("pelis_count", 0) - 1)
                    logger.info(f"🔄 Rescatado '{serie_dest}' ({fname or msg.id}) -> 'Series Infantiles' (Tema ID {topic_id})")
                    await asyncio.sleep(1.2)
                except Exception as e:
                    logger.error(f"Error rescatando mensaje ID {msg.id}: {e}")

        if rescatados > 0:
            logger.info(f"🎉 Total de {rescatados} episodios rescatados y trasladados a Series Infantiles.")
            guardar_progreso(progreso)
        else:
            logger.info("✅ Canal de Películas Infantiles verificado: no se encontraron series coladas.")
    except Exception as e:
        logger.warning(f"Error durante el rescate de películas: {e}")


async def resolve_channel_entity(client: TelegramClient, channel_id, invite_link=None):
    """Obtiene la entidad de un canal o supergrupo asegurando que Telethon use PeerChannel o el enlace de invitación."""
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
        topics_cache = progreso.setdefault("series_topics_cache", {})

        # 1. GESTIÓN CANAL DE PELÍCULAS INFANTILES (Canal Privado Broadcast)
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

        # 2. GESTIÓN CANAL DE SERIES INFANTILES (Supergrupo con FOROS/TEMAS)
        if not progreso.get("canal_series_id"):
            logger.info("Creando supergrupo con temas: 'Series Infantiles'...")
            res_s = await client(CreateChannelRequest(
                title="Series Infantiles",
                about="Canal oficial de Series Infantiles y Caricaturas para TeveFlipe",
                megagroup=True
            ))
            ent_series = res_s.chats[0]
            try:
                await client(ToggleForumRequest(channel=ent_series, enabled=True, tabs=False))
            except TypeError:
                await client(ToggleForumRequest(channel=ent_series, enabled=True))

            inv_s = await client(ExportChatInviteRequest(peer=ent_series))
            s_id = int(f"-100{ent_series.id}") if str(ent_series.id)[0] != '-' else ent_series.id
            progreso["canal_series_id"] = s_id
            progreso["canal_series_link"] = inv_s.link
            logger.info(f"✅ Creado Series Infantiles con Temas: ID={s_id} | Enlace: {inv_s.link}")
            guardar_progreso(progreso)
        else:
            ent_series = await resolve_channel_entity(client, progreso["canal_series_id"], progreso.get("canal_series_link"))

        print("\n" + "═" * 70)
        print("CANALES DESTINO PARA EL PANEL WEB (admin.html):")
        print(f"🎬 Películas Infantiles: ID={progreso['canal_pelis_id']} | Link={progreso['canal_pelis_link']}")
        print(f"📺 Series Infantiles:    ID={progreso['canal_series_id']} | Link={progreso['canal_series_link']}")
        print("═" * 70 + "\n")

        # 3. RESCATE AUTOMÁTICO: Mover cualquier serie que haya ido por error a Películas Infantiles (ej. Fraggle Rock)
        await rescatar_series_de_pelis(client, ent_pelis, ent_series, topics_cache, progreso)

        ultimo_id = progreso.get("last_msg_id", 0)
        total_pelis = progreso.get("pelis_count", 0)
        total_series = progreso.get("series_count", 0)
        total_descartados = progreso.get("descartados", 0)

        logger.info(f"Reanudando desde mensaje ID: {ultimo_id}")
        logger.info(f"Estado previo: {total_pelis} pelis | {total_series} series | {total_descartados} descartados")

        lote_pelis = []
        # Buffers por serie para reenvío agrupado a su tema: { "nombre_serie": [msg_ids...] }
        series_buffers = {}

        total_scanned = 0
        async for msg in client.iter_messages(
            source_entity,
            reply_to=SOURCE_TOPIC_ID,
            min_id=ultimo_id,
            reverse=True
        ):
            ultimo_id = msg.id
            total_scanned += 1

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

            tipo, serie_name = clasificar_contenido(msg)

            if tipo == "PELICULA":
                lote_pelis.append(msg.id)
                total_pelis += 1
                if len(lote_pelis) >= BATCH_SIZE:
                    await forward_batch(client, source_entity, ent_pelis, lote_pelis, topic_id=None, tipo="Películas")
                    lote_pelis.clear()
                    progreso.update({
                        "last_msg_id": ultimo_id,
                        "pelis_count": total_pelis,
                        "series_count": total_series,
                        "descartados": total_descartados
                    })
                    guardar_progreso(progreso)
            else:
                s_name = serie_name or "Serie Infantil"
                if s_name not in series_buffers:
                    series_buffers[s_name] = []
                series_buffers[s_name].append(msg.id)
                total_series += 1

                # Si el buffer de esta serie específica alcanza el tamaño del lote, enviarlo
                if len(series_buffers[s_name]) >= BATCH_SIZE:
                    topic_id = await get_or_create_series_topic(client, ent_series, s_name, topics_cache)
                    await forward_batch(client, source_entity, ent_series, series_buffers[s_name], topic_id=topic_id, tipo=f"Episodios de '{s_name}'")
                    series_buffers[s_name].clear()
                    progreso.update({
                        "last_msg_id": ultimo_id,
                        "pelis_count": total_pelis,
                        "series_count": total_series,
                        "descartados": total_descartados
                    })
                    guardar_progreso(progreso)

            # Cada 100 contenidos procesados, mostrar progreso y vaciar buffers de series pendientes
            if (total_pelis + total_series) % 100 == 0:
                logger.info(f"📊 Progreso: {total_pelis} Películas | {total_series} Episodios procesados...")
                # Enviar buffers de series que tengan al menos 10 episodios acumulados
                for s_key in list(series_buffers.keys()):
                    if len(series_buffers[s_key]) >= 10:
                        t_id = await get_or_create_series_topic(client, ent_series, s_key, topics_cache)
                        await forward_batch(client, source_entity, ent_series, series_buffers[s_key], topic_id=t_id, tipo=f"Episodios de '{s_key}'")
                        series_buffers[s_key].clear()
                progreso.update({
                    "last_msg_id": ultimo_id,
                    "pelis_count": total_pelis,
                    "series_count": total_series,
                    "descartados": total_descartados
                })
                guardar_progreso(progreso)

        # Vaciar remanentes al final
        if lote_pelis:
            await forward_batch(client, source_entity, ent_pelis, lote_pelis, topic_id=None, tipo="Películas")
            lote_pelis.clear()

        for s_key, ids in series_buffers.items():
            if ids:
                t_id = await get_or_create_series_topic(client, ent_series, s_key, topics_cache)
                await forward_batch(client, source_entity, ent_series, ids, topic_id=t_id, tipo=f"Episodios de '{s_key}'")

        progreso.update({
            "last_msg_id": ultimo_id,
            "pelis_count": total_pelis,
            "series_count": total_series,
            "descartados": total_descartados
        })
        guardar_progreso(progreso)

        logger.info("\n🎉 ¡PROCESO DE CLONACIÓN Y CLASIFICACIÓN FINALIZADO!")
        logger.info(f"Total Películas: {total_pelis} | Total Series: {total_series} | Descartados: {total_descartados}")
        logger.info(f"Total de temas de series creados/usados: {len(topics_cache)}")


if __name__ == "__main__":
    asyncio.run(main())
