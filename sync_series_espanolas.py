import asyncio
import json
import logging
import os
import random
import re
import sys
import unicodedata
from collections import defaultdict
from typing import Optional, Dict, List

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import (
    GetForumTopicsRequest,
    CreateForumTopicRequest
)
from telethon.tl.types import (
    MessageMediaDocument,
    MessageMediaPhoto,
    DocumentAttributeVideo,
    DocumentAttributeFilename
)

from sync_bot import (
    clean_series_title,
    is_junk_series_title,
    is_video_message,
    extract_file_name,
    VIDEO_EXTENSIONS
)

logging.basicConfig(
    format="[%(asctime)s] %(levelname)s - %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("SyncEspanolas")

API_ID = int(os.getenv("TELEGRAM_API_ID") or 0)
API_HASH = os.getenv("TELEGRAM_API_HASH") or ""
STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION") or ""

SERIES_SOURCE_CHAT = int(os.getenv("SERIES_SOURCE_CHAT", "-1002160549536"))
SERIES_SOURCE_TOPIC = int(os.getenv("SERIES_SOURCE_TOPIC", "21"))
SERIES_DEST_CHAT = int(os.getenv("SERIES_DEST_CHAT", "-1004419790119"))

STATE_FILE = "sync_state_espanolas.json"
BATCH_FORWARD_LIMIT = int(os.getenv("BATCH_FORWARD_LIMIT", "250"))

SERIES_BLOCKS = [
    (11026, 13693, "El Secreto de Puente Viejo"),
    (13694, 20167, "Cuéntame Cómo Pasó"),
    (20168, 22349, "Al Salir de Clase"),
    (22350, 22803, "Médico de Familia"),
    (22804, 23220, "Aquí No Hay Quien Viva"),
    (23221, 23993, "La Que Se Avecina"),
    (23994, 24686, "7 Vidas"),
    (24687, 33283, "Aída"),
    (33284, 33969, "Los Serrano"),
    (33970, 34224, "Águila Roja"),
    (34225, 34614, "Los Hombres de Paco"),
    (34615, 38592, "Farmacia de Guardia"),
    (38593, 57603, "Bandolera"),
    (57604, 69546, "Nada Es Para Siempre"),
    (69547, 71888, "Regreso a las Sabinas"),
    (71889, 74837, "Salón de Té La Moderna"),
    (74838, 80860, "Hospital Central"),
    (80861, 90316, "Compañeros"),
    (90317, 91652, "Valle Salvaje"),
    (91653, 102985, "SMS (Sin Miedo a Soñar)"),
    (102986, 9999999, "La Verdad de Laura")
]

CANONICAL_ALIASES = {
    "aqui no hay quien viva": "Aquí No Hay Quien Viva",
    "anhqv": "Aquí No Hay Quien Viva",
    "la que se avecina": "La Que Se Avecina",
    "lqsa": "La Que Se Avecina",
    "7 vidas": "7 Vidas",
    "siete vidas": "7 Vidas",
    "aida": "Aída",
    "aída": "Aída",
    "los serrano": "Los Serrano",
    "farmacia de guardia": "Farmacia de Guardia",
    "medico de familia": "Médico de Familia",
    "médico de familia": "Médico de Familia",
    "cuentame como paso": "Cuéntame Cómo Pasó",
    "cuéntame cómo pasó": "Cuéntame Cómo Pasó",
    "cuentame": "Cuéntame Cómo Pasó",
    "el secreto de puente viejo": "El Secreto de Puente Viejo",
    "puente viejo": "El Secreto de Puente Viejo",
    "aguila roja": "Águila Roja",
    "águila roja": "Águila Roja",
    "hospital central": "Hospital Central",
    "los hombres de paco": "Los Hombres de Paco",
    "bandolera": "Bandolera",
    "al salir de clase": "Al Salir de Clase",
    "compañeros": "Compañeros",
    "sms": "SMS (Sin Miedo a Soñar)",
    "sms, sin miedo a soñar": "SMS (Sin Miedo a Soñar)",
    "nada es para siempre": "Nada Es Para Siempre",
    "salon de te la moderna": "Salón de Té La Moderna",
    "salón de té la moderna": "Salón de Té La Moderna",
    "la moderna": "Salón de Té La Moderna",
    "valle salvaje": "Valle Salvaje",
    "regreso a las sabinas": "Regreso a las Sabinas",
    "la verdad de laura": "La Verdad de Laura"
}

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"No se pudo leer {STATE_FILE}: {e}")
    return {
        "last_message_id": 11025,
        "topics_cache": {},
        "forwarded_count": 0,
        "series_stats": {},
        "current_series": None
    }

def save_state(state: dict):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error guardando {STATE_FILE}: {e}")

def resolve_series_for_message(msg_id: int, file_name: str, text: str) -> Optional[str]:
    combined = f"{file_name} {text}".lower()
    for alias, canonical in CANONICAL_ALIASES.items():
        if alias in combined:
            return canonical

    for start_id, end_id, canonical in SERIES_BLOCKS:
        if start_id <= msg_id <= end_id:
            return canonical

    return None

async def get_or_create_topic(client: TelegramClient, dest_chat, series_title: str, state: dict) -> Optional[int]:
    cached = state.setdefault("topics_cache", {})
    norm_key = series_title.strip().lower()
    if norm_key in cached:
        return cached[norm_key]

    dest_input = await client.get_input_entity(dest_chat)

    # 1. Comprobar si ya existe en Telegram
    try:
        offset_date = None
        offset_id = 0
        offset_topic = 0
        while True:
            res = await client(GetForumTopicsRequest(
                peer=dest_input,
                offset_date=offset_date,
                offset_id=offset_id,
                offset_topic=offset_topic,
                limit=100
            ))
            topics = getattr(res, "topics", [])
            if not topics:
                break
            for t in topics:
                t_title = getattr(t, "title", "").strip()
                t_id = getattr(t, "id", None)
                if t_title and t_id:
                    cached[t_title.lower()] = t_id
                    if t_title.lower() == norm_key:
                        state["topics_cache"] = cached
                        save_state(state)
                        return t_id

            if len(topics) < 100:
                break
            last_t = topics[-1]
            offset_topic = getattr(last_t, "id", 0)
            offset_id = getattr(last_t, "top_message", 0)
            offset_date = getattr(last_t, "date", None)
    except Exception as e:
        logger.warning(f"Error consultando temas existentes: {e}")

    if norm_key in cached:
        return cached[norm_key]

    # 2. Crear el tema si no existe
    try:
        logger.info(f"🆕 Creando Tema en 'Series Españolas': '{series_title}'...")
        rand_id = random.randint(1, 2**63 - 1)
        created = await client(CreateForumTopicRequest(
            peer=dest_input,
            title=series_title[:128],
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
            logger.info(f"✅ Tema creado: '{series_title}' (Topic ID: {topic_id})")
            cached[norm_key] = topic_id
            state["topics_cache"] = cached
            save_state(state)
            return topic_id
    except Exception as e:
        logger.error(f"Error creando tema para '{series_title}': {e}")

    return None

async def sync_espanolas():
    if not STRING_SESSION:
        logger.error("TELEGRAM_STRING_SESSION no configurada.")
        return

    state = load_state()
    last_id = state.get("last_message_id", 11025)
    logger.info("=" * 60)
    logger.info("INICIANDO SINCRONIZACIÓN DE SERIES ESPAÑOLAS")
    logger.info(f"Chat Origen: {SERIES_SOURCE_CHAT} (Tema {SERIES_SOURCE_TOPIC})")
    logger.info(f"Chat Destino: {SERIES_DEST_CHAT}")
    logger.info(f"Último ID procesado: {last_id}")
    logger.info(f"Límite de episodios por ejecución: {BATCH_FORWARD_LIMIT}")
    logger.info("=" * 60)

    async with TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH) as client:
        # Precargar entidades de forma robusta
        source_chat = await client.get_entity(SERIES_SOURCE_CHAT)
        
        dest_chat = None
        try:
            dest_chat = await client.get_entity(SERIES_DEST_CHAT)
        except Exception:
            logger.info("Cargando dialogs para resolver el canal destino...")
            async for d in client.iter_dialogs(limit=50):
                if d.id == SERIES_DEST_CHAT or str(SERIES_DEST_CHAT) in str(d.id) or "4419790119" in str(d.id):
                    dest_chat = d.entity
                    break
        if not dest_chat:
            dest_chat = await client.get_entity(SERIES_DEST_CHAT)
            
        dest_input = await client.get_input_entity(dest_chat)

        forward_count = 0
        pending_poster = None
        active_series = state.get("current_series")
        active_topic_id = state.get("topics_cache", {}).get((active_series or "").lower())
        more_remaining = False

        async for msg in client.iter_messages(
            source_chat,
            reply_to=SERIES_SOURCE_TOPIC,
            min_id=last_id,
            reverse=True,
            limit=2500
        ):
            if forward_count >= BATCH_FORWARD_LIMIT:
                logger.info(f"Alcanzado el límite de {BATCH_FORWARD_LIMIT} episodios para esta tanda.")
                more_remaining = True
                break

            text = (msg.text or "").strip()
            fname = extract_file_name(msg)
            resolved_series = resolve_series_for_message(msg.id, fname, text)

            # 1. Carátula o Póster
            if msg.media and isinstance(msg.media, MessageMediaPhoto):
                if resolved_series:
                    active_series = resolved_series
                    active_topic_id = await get_or_create_topic(client, dest_chat, active_series, state)
                    state["current_series"] = active_series
                    pending_poster = msg
                    logger.info(f"🖼️ Póster detectado para serie: '{active_series}'")

            # 2. Archivo de video
            elif is_video_message(msg):
                if resolved_series:
                    active_series = resolved_series
                    active_topic_id = await get_or_create_topic(client, dest_chat, active_series, state)
                    state["current_series"] = active_series

                if not active_topic_id:
                    logger.warning(f"Omitiendo video huérfano sin serie identificada (Msg {msg.id}): {fname}")
                    state["last_message_id"] = msg.id
                    save_state(state)
                    continue

                # Si hay carátula pendiente para este tema, enviarla antes del primer video
                if pending_poster:
                    try:
                        p_caption = pending_poster.text or f"Póster Oficial - {active_series}"
                        await client.send_message(
                            dest_chat,
                            message=p_caption,
                            file=pending_poster.media,
                            reply_to=active_topic_id
                        )
                        logger.info(f"🖼️ Póster enviado al tema '{active_series}'")
                        pending_poster = None
                        await asyncio.sleep(1.5)
                    except Exception as e:
                        logger.warning(f"Error enviando póster: {e}")

                # Enviar episodio
                try:
                    caption = text or fname or "Episodio"
                    await client.send_message(
                        dest_chat,
                        message=caption,
                        file=msg.media,
                        reply_to=active_topic_id
                    )
                    forward_count += 1
                    state["forwarded_count"] = state.get("forwarded_count", 0) + 1
                    state["series_stats"].setdefault(active_series, 0)
                    state["series_stats"][active_series] += 1

                    logger.info(f"[{forward_count}/{BATCH_FORWARD_LIMIT}] 🎬 Enviado a '{active_series}': {fname or msg.id}")
                    state["last_message_id"] = msg.id
                    save_state(state)
                    await asyncio.sleep(2.0)
                except Exception as ex:
                    logger.error(f"Error enviando episodio Msg {msg.id}: {ex}")
                    await asyncio.sleep(3.0)

            # Actualizar último ID procesado
            if msg.id > state.get("last_message_id", 0):
                state["last_message_id"] = msg.id
                save_state(state)

        logger.info("=" * 60)
        logger.info(f"Tanda finalizada. Episodios reenviados en esta ejecución: {forward_count}")
        logger.info(f"Total histórico reenviado: {state.get('forwarded_count', 0)}")
        logger.info(f"Último ID alcanzado: {state.get('last_message_id', 0)}")
        logger.info("=" * 60)

        # Escribir archivo indicador para encadenar la siguiente ejecución
        if more_remaining or forward_count >= BATCH_FORWARD_LIMIT:
            with open(".more_episodes", "w") as f:
                f.write("true")
        elif os.path.exists(".more_episodes"):
            os.remove(".more_episodes")

if __name__ == "__main__":
    asyncio.run(sync_espanolas())
