import asyncio
import os
import json
import random
import re
import logging
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import (
    GetForumTopicsRequest,
    CreateForumTopicRequest,
    DeleteTopicHistoryRequest,
    EditForumTopicRequest
)
from telethon.tl.types import MessageMediaDocument, DocumentAttributeFilename, DocumentAttributeVideo

logging.basicConfig(
    format="[%(asctime)s] %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("RepararTransformers")

API_ID = int(os.environ.get("TELEGRAM_API_ID", "28045969"))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION = os.environ.get("TELEGRAM_STRING_SESSION", "")
TARGET_CHAT = int(os.environ.get("TARGET_CHAT", "-1002097175258"))
STATE_FILE = "sync_state.json"

SERIES_GROUPS = [
    {
        "name": "Transformers (G1)",
        "min_id": 17429,
        "max_id": 17625,
        "aliases": ["transformers g1", "transformers generacion 1", "transformers: generacion 1", "transformers"]
    },
    {
        "name": "Transformers: The Headmasters",
        "min_id": 17626,
        "max_id": 17696,
        "aliases": ["transformers headmasters", "transformers the headmasters", "the headmasters"]
    },
    {
        "name": "Transformers: Super-God Masterforce",
        "min_id": 17697,
        "max_id": 17781,
        "aliases": ["transformers super god masterforce", "super god masterforce", "masterforce"]
    },
    {
        "name": "Transformers: Victory",
        "min_id": 17782,
        "max_id": 17858,
        "aliases": ["transformers victory", "victory"]
    },
    {
        "name": "Transformers: Beast Wars",
        "min_id": 17859,
        "max_id": 17963,
        "aliases": ["transformers beast wars", "beast wars", "guerra de bestias"]
    },
    {
        "name": "Transformers: Beast Machines",
        "min_id": 17964,
        "max_id": 18016,
        "aliases": ["transformers beast machines", "beast machines"]
    },
    {
        "name": "Transformers: Beast Wars II",
        "min_id": 18017,
        "max_id": 18101,
        "aliases": ["transformers beast wars 2", "transformers beast wars ii", "beast wars 2", "beast wars ii"]
    },
    {
        "name": "Transformers: Beast Wars Neo",
        "min_id": 18102,
        "max_id": 18172,
        "aliases": ["transformers beast wars neo", "beast wars neo"]
    },
    {
        "name": "Transformers: Robot Masters",
        "min_id": 18173,
        "max_id": 18177,
        "aliases": ["transformers robot masters", "robot masters", "beast wars especiales"]
    },
    {
        "name": "Transformers: Robots in Disguise",
        "min_id": 18178,
        "max_id": 18256,
        "aliases": ["transformers robots in disguise", "robots in disguise"]
    }
]


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"No se pudo leer {STATE_FILE}: {e}")
    return {}


def save_state(state: dict):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        logger.info(f"Estado guardado en {STATE_FILE}")
    except Exception as e:
        logger.error(f"Error guardando {STATE_FILE}: {e}")


async def fetch_all_topics(client, chat) -> list:
    logger.info("Listando todos los temas existentes en el supergrupo...")
    all_topics = []
    offset_date = None
    offset_id = 0
    offset_topic = 0
    while True:
        try:
            res = await client(GetForumTopicsRequest(
                peer=chat,
                offset_date=offset_date,
                offset_id=offset_id,
                offset_topic=offset_topic,
                limit=100
            ))
            topics = getattr(res, "topics", [])
            if not topics:
                break
            all_topics.extend(topics)
            last = topics[-1]
            offset_topic = getattr(last, "id", 0)
            offset_id = getattr(last, "top_message", 0)
            offset_date = getattr(last, "date", None)
            if len(topics) < 100:
                break
        except errors.FloodWaitError as e:
            logger.warning(f"FloodWait listando temas: esperando {e.seconds}s...")
            await asyncio.sleep(e.seconds + 2)
        except Exception as e:
            logger.error(f"Error listando temas: {e}")
            break
    logger.info(f"Total de temas encontrados en el foro: {len(all_topics)}")
    return all_topics


async def get_or_create_official_topic(client, chat, group_info: dict, all_topics: list) -> int:
    name = group_info["name"]
    aliases = [a.lower() for a in group_info["aliases"]] + [name.lower()]

    for t in all_topics:
        t_title = getattr(t, "title", "").strip().lower()
        t_id = getattr(t, "id", 0)
        # Excluir temas temporales si están en el rango de desvíos
        if group_info["min_id"] <= t_id <= group_info["max_id"]:
            continue
        if t_title in aliases:
            logger.info(f"🎯 Tema oficial existente encontrado para '{name}': ID {t_id}")
            return t_id

    # Si no existe fuera del rango de desvíos, crear el tema oficial
    logger.info(f"🆕 Creando tema oficial para '{name}'...")
    while True:
        try:
            rand_id = random.randint(1, 2**63 - 1)
            created = await client(CreateForumTopicRequest(
                peer=chat,
                title=name[:128],
                random_id=rand_id
            ))
            official_id = None
            for update in getattr(created, "updates", []):
                msg = getattr(update, "message", None)
                if msg and hasattr(msg, "id"):
                    action = getattr(msg, "action", None)
                    if action and "TopicCreate" in type(action).__name__:
                        official_id = msg.id
                        break
                    elif official_id is None:
                        official_id = msg.id
                elif hasattr(update, "id"):
                    official_id = update.id
            if official_id:
                logger.info(f"✅ Tema oficial creado: '{name}' (ID {official_id})")
                return official_id
        except errors.FloodWaitError as e:
            logger.warning(f"FloodWait creando tema '{name}': esperando {e.seconds}s...")
            await asyncio.sleep(e.seconds + 2)
        except Exception as e:
            logger.error(f"Error creando tema '{name}': {e}")
            await asyncio.sleep(2)
            break

    raise RuntimeError(f"No se pudo crear ni encontrar el tema oficial para '{name}'")


async def main():
    if not SESSION:
        logger.error("❌ ERROR: TELEGRAM_STRING_SESSION no configurada.")
        return

    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        chat = await client.get_entity(TARGET_CHAT)
        logger.info("=" * 70)
        logger.info(f"REPARACIÓN Y CONSOLIDACIÓN DE TRANSFORMERS EN: {chat.title} ({chat.id})")
        logger.info("=" * 70)

        state = load_state()
        cached_topics = state.setdefault("series_topics_cache", {})

        all_topics = await fetch_all_topics(client, chat)
        topics_by_id = {getattr(t, "id"): t for t in all_topics}

        total_transferred_all = 0
        total_deleted_all = 0

        for s_idx, group in enumerate(SERIES_GROUPS, 1):
            name = group["name"]
            min_id = group["min_id"]
            max_id = group["max_id"]

            logger.info("")
            logger.info(f"[{s_idx}/{len(SERIES_GROUPS)}] === Procesando '{name}' (Rango IDs: {min_id} - {max_id}) ===")

            official_id = await get_or_create_official_topic(client, chat, group, all_topics)

            # Buscar todos los temas huérfanos que caen en este rango
            stray_ids = [
                tid for tid in sorted(topics_by_id.keys())
                if min_id <= tid <= max_id and tid != official_id
            ]

            # También incluir IDs conocidos en caché que coincidan con este rango
            for k, v in list(cached_topics.items()):
                if min_id <= v <= max_id and v != official_id and v not in stray_ids:
                    stray_ids.append(v)
            stray_ids = sorted(set(stray_ids))

            logger.info(f"Temas individuales a consolidar para '{name}': {len(stray_ids)}")

            transferred_group = 0
            for idx, tid in enumerate(stray_ids, 1):
                t_obj = topics_by_id.get(tid)
                title = getattr(t_obj, "title", f"ID_{tid}")

                # Obtener mensajes del tema huérfano (en orden cronológico: poster primero, luego video)
                msgs = []
                while True:
                    try:
                        async for m in client.iter_messages(chat, reply_to=tid, reverse=True):
                            if m.media:
                                msgs.append(m)
                        break
                    except errors.FloodWaitError as e:
                        logger.warning(f"FloodWait leyendo mensajes de tema {tid}: esperando {e.seconds}s...")
                        await asyncio.sleep(e.seconds + 2)
                    except Exception as e:
                        logger.warning(f"Error leyendo tema {tid}: {e}")
                        break

                for m in msgs:
                    caption = m.text or (m.file.name if getattr(m, "file", None) and getattr(m.file, "name", None) else "")
                    fname = getattr(m.file, "name", None) if getattr(m, "file", None) else m.id
                    while True:
                        try:
                            await client.send_message(
                                chat,
                                message=caption,
                                file=m.media,
                                reply_to=official_id
                            )
                            transferred_group += 1
                            total_transferred_all += 1
                            break
                        except errors.FloodWaitError as e:
                            logger.warning(f"FloodWait enviando archivo {fname}: esperando {e.seconds}s...")
                            await asyncio.sleep(e.seconds + 2)
                        except Exception as e:
                            logger.error(f"Error enviando mensaje ID {m.id}: {e}")
                            break
                    await asyncio.sleep(1.2)

                # Eliminar tema huérfano
                while True:
                    try:
                        await client(DeleteTopicHistoryRequest(peer=chat, top_msg_id=tid))
                        total_deleted_all += 1
                        break
                    except errors.FloodWaitError as e:
                        logger.warning(f"FloodWait borrando tema {tid}: esperando {e.seconds}s...")
                        await asyncio.sleep(e.seconds + 2)
                    except Exception as e:
                        logger.warning(f"Aviso eliminando tema {tid}: {e}")
                        break
                await asyncio.sleep(0.4)

                if idx % 10 == 0 or idx == len(stray_ids):
                    logger.info(f"  -> Progreso '{name}': {idx}/{len(stray_ids)} temas procesados ({transferred_group} archivos transferidos)")

            # Limpiar caché de los IDs huérfanos
            stray_set = set(stray_ids)
            for k, v in list(cached_topics.items()):
                if v in stray_set:
                    del cached_topics[k]

            # Registrar tema oficial en la caché
            cached_topics[name.lower()] = official_id
            for a in group["aliases"]:
                cached_topics[a.lower()] = official_id

            state["series_topics_cache"] = cached_topics
            save_state(state)
            logger.info(f"✅ '{name}' consolidada: {transferred_group} mensajes en Topic ID {official_id}")

        # Limpieza final de caché para cualquier clave residual con numeración o IDs de 17429 a 18256
        for k, v in list(cached_topics.items()):
            if 17429 <= v <= 18256:
                del cached_topics[k]
            elif re.match(r"^(\d{1,3})\s*[-–—.:_]\s*", k):
                del cached_topics[k]

        state["series_topics_cache"] = cached_topics
        save_state(state)

        logger.info("")
        logger.info("=" * 70)
        logger.info(f"🎉 CONSOLIDACIÓN COMPLETA: {total_transferred_all} archivos transferidos, {total_deleted_all} temas huérfanos eliminados.")
        logger.info("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
