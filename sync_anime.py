import asyncio
import json
import logging
import os
import random
import re
from telethon import TelegramClient, utils, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import (
    ForwardMessagesRequest,
    CreateForumTopicRequest
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("SyncAnime")

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION = os.environ["TELEGRAM_STRING_SESSION"]

CONFIG_FILE = "anime_config.json"
STATE_FILE = "sync_state_anime.json"
ANALYSIS_FILE = "analisis_anime.json"

BATCH_SIZE = int(os.getenv("BATCH_SIZE", "25"))
SERIES_LIMIT = int(os.getenv("SERIES_LIMIT", "50"))  # Límite de series por ejecución para no exceder timeout
SYNC_MODE = os.getenv("SYNC_MODE", "all")  # "all", "movies", "series"

def load_json(filepath: str, default=None):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Error leyendo {filepath}: {e}")
    return default() if callable(default) else (default or {})

def save_json(filepath: str, data: dict):
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error guardando {filepath}: {e}")

async def get_or_create_topic(client: TelegramClient, group_entity, series_title: str, state: dict) -> int:
    """Crea o recupera el tema correspondiente a la serie en el supergrupo."""
    topics_map = state.setdefault("series_topics", {})
    norm_key = series_title.strip().lower()

    if norm_key in topics_map:
        return topics_map[norm_key]

    clean_name = series_title.strip()[:128]
    colors = [0x6FB9F0, 0xFFD67E, 0xCB86DB, 0x8EEE98, 0xFF93B2, 0xFB6F5F]

    intentos = 0
    while intentos < 5:
        intentos += 1
        try:
            rand_id = random.randint(1, 2**63 - 1)
            created = await client(CreateForumTopicRequest(
                peer=group_entity,
                title=clean_name,
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
                logger.info(f"✨ Tema creado: '{clean_name}' (ID Topic: {topic_id})")
                topics_map[norm_key] = topic_id
                save_json(STATE_FILE, state)
                await asyncio.sleep(2.0)
                return topic_id
        except errors.FloodWaitError as e:
            logger.warning(f"⏳ FloodWait creando tema '{clean_name}': esperando {e.seconds + 2}s...")
            await asyncio.sleep(e.seconds + 2)
        except Exception as e:
            logger.error(f"Error creando tema '{clean_name}': {e}")
            break

    return None

async def forward_chunk_safe(client: TelegramClient, source_peer, dest_peer, msg_ids: list, top_msg_id: int = None, desc: str = "") -> bool:
    """Reenvía un lote de mensajes sin remitente (drop_author=True) de forma segura."""
    if not msg_ids:
        return True

    rand_ids = [random.randint(1, 2**63 - 1) for _ in msg_ids]
    intentos = 0
    while intentos < 5:
        intentos += 1
        try:
            kwargs = {
                "from_peer": source_peer,
                "to_peer": dest_peer,
                "id": msg_ids,
                "random_id": rand_ids,
                "drop_author": True
            }
            if top_msg_id:
                kwargs["top_msg_id"] = top_msg_id

            await client(ForwardMessagesRequest(**kwargs))
            logger.info(f"🚀 Lote reenviado ({len(msg_ids)} msgs) a {desc} sin remitente.")
            await asyncio.sleep(random.uniform(2.5, 3.8))
            return True
        except errors.FloodWaitError as e:
            logger.warning(f"⏳ Telegram FloodWait: esperando {e.seconds + 3}s...")
            await asyncio.sleep(e.seconds + 3)
        except errors.ChatForwardsRestrictedError:
            logger.warning("⚠️ Canal origen protegido contra reenvíos directos.")
            return False
        except Exception as e:
            logger.warning(f"Aviso en lote ({desc}) intento {intentos}: {e}")
            await asyncio.sleep(2.0)

    return False

async def sync_movies(client, source_entity, movies_channel, analysis_data, state):
    """Sincroniza las películas detectadas al canal de Películas Anime."""
    logger.info("\n" + "=" * 60)
    logger.info(" INICIANDO SINCRONIZACIÓN DE PELÍCULAS ANIME")
    logger.info("=" * 60)

    synced_movies = set(state.setdefault("synced_movie_ids", []))
    peliculas = analysis_data.get("peliculas", [])

    # Filtrar solo películas válidas
    pending_pelis = [p for p in peliculas if p["message_id"] not in synced_movies and len(p.get("title", "")) > 1]
    logger.info(f"Total películas detectadas: {len(peliculas)} | Ya sincronizadas: {len(synced_movies)} | Pendientes: {len(pending_pelis)}")

    if not pending_pelis:
        logger.info("✅ Todas las películas anime ya están sincronizadas.")
        return

    # Procesar en lotes
    chunk_size = min(BATCH_SIZE, 20)
    for i in range(0, len(pending_pelis), chunk_size):
        chunk = pending_pelis[i:i + chunk_size]
        msg_ids = [p["message_id"] for p in chunk]

        ok = await forward_chunk_safe(
            client=client,
            source_peer=source_entity,
            dest_peer=movies_channel,
            msg_ids=msg_ids,
            top_msg_id=None,
            desc="🎬 Películas Anime"
        )
        if ok:
            synced_movies.update(msg_ids)
            state["synced_movie_ids"] = list(synced_movies)
            save_json(STATE_FILE, state)
            logger.info(f"Progreso películas: {len(synced_movies)} / {len(peliculas)}")
        else:
            logger.error("Error persistente al reenviar lote de películas. Abortando bloque actual.")
            break

async def sync_series(client, source_entity, series_group, analysis_data, state):
    """Sincroniza las series anime al supergrupo de Series Anime, creando 1 tema por serie."""
    logger.info("\n" + "=" * 60)
    logger.info(" INICIANDO SINCRONIZACIÓN DE SERIES ANIME (POR TEMAS)")
    logger.info("=" * 60)

    completed_series = set(state.setdefault("completed_series", []))
    all_series = list(analysis_data.get("series", {}).values())

    # Filtrar series elegibles (con nombre válido y al menos 2 episodios)
    eligible = [
        s for s in all_series
        if s["total_episodes"] >= 2 and len(s["title"]) > 2 and not s["title"].startswith("01X")
    ]
    # Ordenar por cantidad de episodios (las más populares y extensas primero)
    eligible.sort(key=lambda x: x["total_episodes"], reverse=True)

    pending_series = [s for s in eligible if s["title"] not in completed_series]
    logger.info(f"Total series identificadas: {len(eligible)} | Completadas: {len(completed_series)} | Pendientes: {len(pending_series)}")

    if not pending_series:
        logger.info("✅ Todas las series anime catalogadas ya están sincronizadas.")
        return

    # En cada ejecución tomamos hasta SERIES_LIMIT para no saturar
    to_process = pending_series[:SERIES_LIMIT]
    logger.info(f"Procesando lote de {len(to_process)} series en esta tanda...")

    for idx, s in enumerate(to_process, 1):
        series_title = s["title"]
        logger.info(f"\n[{idx}/{len(to_process)}] 📺 Serie: '{series_title}' ({s['total_episodes']} episodios, {s['total_size_gb']} GB)")

        # 1. Crear u obtener el tema de la serie
        topic_id = await get_or_create_topic(client, series_group, series_title, state)
        if not topic_id:
            logger.warning(f"No se pudo crear tema para '{series_title}'. Omitiendo temporalmente.")
            continue

        # 2. Obtener lista de IDs de mensajes para esta serie
        # Si vienen en el análisis o recopilando los mensajes
        # Usamos el rango msg_range para extraer los mensajes
        msg_range = s.get("msg_range", "")
        series_msg_ids = []
        if msg_range and " - " in msg_range:
            parts = msg_range.split(" - ")
            try:
                min_id = int(parts[0])
                max_id = int(parts[1])
                # Buscar mensajes del tema origen correspondientes
                async for m in client.iter_messages(
                    source_entity,
                    reply_to=analysis_data.get("topic_id", 316312),
                    min_id=min_id - 1,
                    max_id=max_id + 1,
                    reverse=True
                ):
                    if m.media and getattr(m, "video", None) or (m.file and m.file.name):
                        fn = m.file.name if (m.file and m.file.name) else (m.text or "")
                        # Si coincide con el título de la serie
                        if series_title.lower() in fn.lower() or series_title.lower() in (m.text or "").lower():
                            series_msg_ids.append(m.id)
            except Exception as e:
                logger.warning(f"Error extrayendo IDs para '{series_title}': {e}")

        if not series_msg_ids:
            logger.info(f"No se encontraron mensajes específicos en rango para '{series_title}'. Marcando.")
            completed_series.add(series_title)
            state["completed_series"] = list(completed_series)
            save_json(STATE_FILE, state)
            continue

        # Reenviar episodios en lotes dentro del tema
        logger.info(f"Reenviando {len(series_msg_ids)} episodios al tema ID {topic_id}...")
        chunk_size = BATCH_SIZE
        series_success = True
        for ci in range(0, len(series_msg_ids), chunk_size):
            chunk = series_msg_ids[ci:ci + chunk_size]
            ok = await forward_chunk_safe(
                client=client,
                source_peer=source_entity,
                dest_peer=series_group,
                msg_ids=chunk,
                top_msg_id=topic_id,
                desc=f"Tema: {series_title}"
            )
            if not ok:
                series_success = False
                break

        if series_success:
            completed_series.add(series_title)
            state["completed_series"] = list(completed_series)
            save_json(STATE_FILE, state)
            logger.info(f"✅ Serie '{series_title}' completada con éxito.")

        await asyncio.sleep(2.0)

async def main():
    config = load_json(CONFIG_FILE)
    if not config or "movies_channel_id" not in config or "series_group_id" not in config:
        logger.error(f"Archivo de configuración '{CONFIG_FILE}' incompleto o inexistente. Ejecuta crear_canales_anime primero.")
        return

    analysis = load_json(ANALYSIS_FILE)
    if not analysis:
        logger.error(f"Archivo de análisis '{ANALYSIS_FILE}' no encontrado.")
        return

    state = load_json(STATE_FILE, default=dict)

    source_chat_id = config["source_chat_id"]
    movies_channel_id = config["movies_channel_id"]
    series_group_id = config["series_group_id"]

    logger.info("Conectando con Telegram...")
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        me = await client.get_me()
        logger.info(f"Conectado como: {me.first_name} (@{me.username or 'sin_username'})")

        source_entity = await client.get_entity(source_chat_id)
        movies_channel = await client.get_entity(movies_channel_id)
        series_group = await client.get_entity(series_group_id)

        logger.info(f"Canal Origen: {getattr(source_entity, 'title', source_chat_id)}")
        logger.info(f"Destino Películas: {getattr(movies_channel, 'title', movies_channel_id)}")
        logger.info(f"Destino Series: {getattr(series_group, 'title', series_group_id)}")

        if SYNC_MODE in ("all", "movies"):
            await sync_movies(client, source_entity, movies_channel, analysis, state)

        if SYNC_MODE in ("all", "series"):
            await sync_series(client, source_entity, series_group, analysis, state)

        logger.info("\n🎉 Sesión de sincronización finalizada con éxito.")

if __name__ == "__main__":
    asyncio.run(main())
