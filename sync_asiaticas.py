import asyncio
import json
import logging
import os
import random
import sys
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
logger = logging.getLogger("SyncAsiaticas")

API_ID = int(os.getenv("TELEGRAM_API_ID") or 0)
API_HASH = os.getenv("TELEGRAM_API_HASH") or ""
SESSION = os.getenv("TELEGRAM_STRING_SESSION") or ""

CONFIG_FILE = "config_asiaticas.json"
STATE_FILE = "sync_state_asiaticas.json"
AUDIT_FILE = "auditoria_series_asiaticas.json"

SERIES_BATCH_LIMIT = int(os.getenv("SERIES_BATCH_LIMIT", "15"))  # Series a procesar por ejecución
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "5"))                  # Mensajes por lote de reenvío

TOPIC_COLORS = [0x6FB9F0, 0xFFD67E, 0xCB86DB, 0x8EEE98, 0xFF93B2, 0xFB6F5F]

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

async def get_or_create_topic(client: TelegramClient, dest_peer, series_title: str, state: dict) -> int:
    topics_map = state.setdefault("series_topics", {})
    norm_key = series_title.strip().lower()

    if norm_key in topics_map:
        return topics_map[norm_key]

    clean_name = series_title.strip()[:120]
    intentos = 0
    while intentos < 5:
        intentos += 1
        try:
            rand_id = random.randint(1, 2**63 - 1)
            created = await client(CreateForumTopicRequest(
                peer=dest_peer,
                title=clean_name,
                icon_color=random.choice(TOPIC_COLORS),
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
                await asyncio.sleep(2.5)
                return topic_id
        except errors.FloodWaitError as e:
            wait_time = e.seconds + 5
            logger.warning(f"⏳ FloodWait creando tema '{clean_name}': esperando {wait_time}s...")
            await asyncio.sleep(wait_time)
        except Exception as e:
            logger.error(f"Error creando tema '{clean_name}': {e}")
            break

    return None

async def forward_chunk_safe(client: TelegramClient, source_peer, dest_peer, msg_ids: list, top_msg_id: int, desc: str = "") -> bool:
    if not msg_ids:
        return True

    rand_ids = [random.randint(1, 2**63 - 1) for _ in msg_ids]
    intentos = 0
    while intentos < 5:
        intentos += 1
        try:
            await client(ForwardMessagesRequest(
                from_peer=source_peer,
                to_peer=dest_peer,
                id=msg_ids,
                random_id=rand_ids,
                drop_author=True,
                top_msg_id=top_msg_id
            ))
            logger.info(f"🚀 Reenviados {len(msg_ids)} msgs a '{desc}' (Topic {top_msg_id}) sin remitente.")
            # Respetar tiempos de Telegram de manera segura
            await asyncio.sleep(random.uniform(3.0, 4.5))
            return True
        except errors.FloodWaitError as e:
            wait_time = e.seconds + 5
            logger.warning(f"⏳ Telegram FloodWait: esperando {wait_time}s...")
            await asyncio.sleep(wait_time)
        except errors.ChatForwardsRestrictedError:
            logger.error("❌ El canal origen no permite reenvío directo de archivos.")
            return False
        except Exception as e:
            logger.warning(f"Aviso en lote ({desc}) intento {intentos}: {e}")
            await asyncio.sleep(3.0)

    return False

async def main():
    if not SESSION:
        logger.error("TELEGRAM_STRING_SESSION no configurada.")
        sys.exit(1)

    config = load_json(CONFIG_FILE)
    if not config or "id" not in config:
        logger.error(f"No se encontró configuración válida en {CONFIG_FILE}. Asegúrate de crear el grupo primero.")
        sys.exit(1)

    dest_chat_id = int(config["id"])
    source_chat_id = int(config.get("source_chat_id", -1002160549536))
    
    audit_data = load_json(AUDIT_FILE)
    if not audit_data or "series" not in audit_data:
        logger.error(f"No se encontró archivo de auditoría {AUDIT_FILE}.")
        sys.exit(1)

    state = load_json(STATE_FILE, default=lambda: {
        "series_topics": {},
        "completed_series": [],
        "synced_message_ids": []
    })

    synced_msgs_set = set(state.setdefault("synced_message_ids", []))
    completed_series_set = set(state.setdefault("completed_series", []))

    logger.info(f"Iniciando sincronización hacia destino '{config.get('title')}' (ID: {dest_chat_id})...")
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        source_peer = await client.get_input_entity(source_chat_id)
        dest_peer = await client.get_input_entity(dest_chat_id)

        all_series = audit_data["series"]
        # Filtrar series pendientes
        pending_series = [s for s in all_series if s["titulo"].strip().lower() not in completed_series_set]
        logger.info(f"Total series en auditoría: {len(all_series)} | Pendientes: {len(pending_series)}")

        processed_series_count = 0

        for s in pending_series:
            if processed_series_count >= SERIES_BATCH_LIMIT:
                logger.info(f"Alcanzado el límite por lote ({SERIES_BATCH_LIMIT} series). Guardando progreso.")
                break

            stitle = s["titulo"]
            norm_key = stitle.strip().lower()
            logger.info(f"\n==================================================")
            logger.info(f"📦 Procesando serie ({processed_series_count + 1}/{min(len(pending_series), SERIES_BATCH_LIMIT)}): '{stitle}'")

            # 1. Obtener o crear tema en el supergrupo destino
            topic_id = await get_or_create_topic(client, dest_peer, stitle, state)
            if not topic_id:
                logger.error(f"No se pudo crear/obtener tema para '{stitle}', saltando...")
                continue

            # 2. Reenviar carátula / ficha si existe y no ha sido enviada
            poster_id = s.get("poster_msg_id")
            if poster_id and poster_id not in synced_msgs_set:
                logger.info(f"Enviando carátula / ficha (Msg ID: {poster_id})...")
                ok = await forward_chunk_safe(client, source_peer, dest_peer, [poster_id], topic_id, desc=f"{stitle} [Poster]")
                if ok:
                    synced_msgs_set.add(poster_id)
                    state["synced_message_ids"].append(poster_id)
                    save_json(STATE_FILE, state)

            # 3. Recopilar todos los mensajes de video de todas las temporadas
            video_msg_ids = []
            for t_name, t_info in s["temporadas"].items():
                for ep in t_info["episodios_detalle"]:
                    for m_id in ep.get("msg_ids", []):
                        if m_id not in video_msg_ids and m_id not in synced_msgs_set:
                            video_msg_ids.append(m_id)

            logger.info(f"Episodios pendientes de reenvío para '{stitle}': {len(video_msg_ids)}")

            # 4. Reenviar en lotes (chunks) ordenados cronológicamente
            all_episodes_synced = True
            for i in range(0, len(video_msg_ids), CHUNK_SIZE):
                chunk = video_msg_ids[i:i + CHUNK_SIZE]
                ok = await forward_chunk_safe(client, source_peer, dest_peer, chunk, topic_id, desc=f"{stitle} [Caps {i+1}-{i+len(chunk)}]")
                if ok:
                    for m_id in chunk:
                        synced_msgs_set.add(m_id)
                        state["synced_message_ids"].append(m_id)
                    save_json(STATE_FILE, state)
                else:
                    all_episodes_synced = False
                    logger.warning(f"Fallo reenviando lote en '{stitle}'. Se continuará en la próxima ejecución.")
                    break

            if all_episodes_synced:
                logger.info(f"✅ ¡Serie '{stitle}' sincronizada completamente!")
                completed_series_set.add(norm_key)
                state["completed_series"].append(norm_key)
                save_json(STATE_FILE, state)

            processed_series_count += 1
            # Pausa de cortesía entre series
            await asyncio.sleep(random.uniform(4.0, 6.0))

        logger.info("\n==================================================")
        logger.info(f"🎉 Ejecución de sincronización finalizada.")
        logger.info(f"Series procesadas en este turno: {processed_series_count}")
        logger.info(f"Total series completadas acumuladas: {len(state['completed_series'])} / {len(all_series)}")
        logger.info(f"Total mensajes multimedia sincronizados: {len(state['synced_message_ids'])}")
        save_json(STATE_FILE, state)

if __name__ == "__main__":
    asyncio.run(main())
