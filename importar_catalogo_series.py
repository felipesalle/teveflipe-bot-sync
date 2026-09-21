#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
importar_catalogo_series.py
Importador masivo e inteligente de series hacia Supergrupos de Telegram con soporte de Foros/Temas.
Gestiona creación de Topics anti-duplicados, reenvío ordenado por lotes y persistencia con checkpoints.
"""

import os
import sys
import re
import json
import time
import random
import asyncio
import logging
import argparse
from typing import Dict, List, Any, Optional

from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import (
    GetForumTopicsRequest,
    CreateForumTopicRequest,
    ForwardMessagesRequest,
)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("ImportadorSeries")

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION", "")
DEFAULT_SOURCE_CHAT = int(os.getenv("SERIES_SOURCE_CHAT", "-1002257262928"))
PROGRESS_FILE = "progreso_importacion.json"


def load_progress() -> Dict[str, Any]:
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"No se pudo cargar progreso anterior: {e}")
    return {"completed_series": {}, "topics_cache": {}}


def save_progress(progress: Dict[str, Any]):
    try:
        tmp_file = PROGRESS_FILE + ".tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(progress, f, indent=2, ensure_ascii=False)
        os.replace(tmp_file, PROGRESS_FILE)
    except Exception as e:
        logger.error(f"Error guardando {PROGRESS_FILE}: {e}")


async def get_existing_forum_topics(client: TelegramClient, dest_entity) -> Dict[str, int]:
    """Obtiene todos los temas existentes en el supergrupo para evitar duplicados."""
    topics_map: Dict[str, int] = {}
    try:
        offset_date = None
        offset_id = 0
        offset_topic = 0

        while True:
            res = await client(GetForumTopicsRequest(
                peer=dest_entity,
                offset_date=offset_date,
                offset_id=offset_id,
                offset_topic=offset_topic,
                limit=100
            ))
            topics = getattr(res, "topics", [])
            if not topics:
                break

            for t in topics:
                title = getattr(t, "title", "").strip().lower()
                topic_id = getattr(t, "id", None)
                if title and topic_id:
                    topics_map[title] = topic_id

            if len(topics) < 100:
                break

            last = topics[-1]
            offset_topic = getattr(last, "id", 0)
            offset_id = getattr(last, "top_message", 0)
            offset_date = getattr(last, "date", None)

    except Exception as e:
        logger.warning(f"Advertencia al consultar temas existentes: {e}")

    logger.info(f"Temas existentes detectados en el supergrupo: {len(topics_map)}")
    return topics_map


async def get_or_create_topic(
    client: TelegramClient,
    dest_entity,
    series_name: str,
    topics_map: Dict[str, int]
) -> Optional[int]:
    """Busca si el tema ya existe o crea uno nuevo de forma segura."""
    norm_name = series_name.strip().lower()

    # 1. Búsqueda exacta
    if norm_name in topics_map:
        return topics_map[norm_name]

    # 2. Búsqueda aproximada (por si hay pequeñas variaciones de acentos o puntuación)
    for existing_title, tid in topics_map.items():
        if norm_name == existing_title or norm_name in existing_title or existing_title in norm_name:
            if len(norm_name) >= 4:
                topics_map[norm_name] = tid
                return tid

    # 3. Crear nuevo tema
    clean_title = series_name.strip()[:128]
    while True:
        try:
            logger.info(f"🆕 Creando nuevo tema en supergrupo: '{clean_title}'...")
            rand_id = random.randint(1, 2**63 - 1)
            created = await client(CreateForumTopicRequest(
                peer=dest_entity,
                title=clean_title,
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

            if topic_id:
                logger.info(f"✅ Tema creado con éxito: '{clean_title}' (Topic ID: {topic_id})")
                topics_map[norm_name] = topic_id
                await asyncio.sleep(1.0)
                return topic_id

            logger.warning(f"No se pudo determinar el ID del tema recién creado para '{clean_title}'.")
            return None

        except errors.FloodWaitError as e:
            logger.warning(f"FloodWait al crear tema: esperando {e.seconds + 2}s...")
            await asyncio.sleep(e.seconds + 2)
        except Exception as e:
            logger.error(f"Error creando tema '{clean_title}': {e}")
            return None


async def resolve_entity_robust(client: TelegramClient, target: Any):
    target_str = str(target).strip(" '\"")

    # Si coincide con clave en config_supergrupos_series.json (ej: turcas_y_telenovelas)
    if os.path.exists("config_supergrupos_series.json"):
        try:
            with open("config_supergrupos_series.json", "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if target_str in cfg:
                item = cfg[target_str]
                if item.get("invite_link"):
                    try:
                        return await client.get_entity(item["invite_link"])
                    except Exception:
                        pass
                if item.get("id"):
                    target_str = str(item["id"])
            else:
                for item in cfg.values():
                    if str(item.get("id")) == target_str and item.get("invite_link"):
                        try:
                            return await client.get_entity(item["invite_link"])
                        except Exception:
                            pass
        except Exception as e:
            logger.warning(f"Aviso leyendo config_supergrupos_series.json: {e}")

    if re.match(r"^-?\d+$", target_str):
        num_id = int(target_str)
        try:
            return await client.get_entity(num_id)
        except Exception:
            pass

        try:
            dialogs = await client.get_dialogs(limit=150)
            for d in dialogs:
                if d.id == num_id:
                    return d.entity
            return await client.get_entity(num_id)
        except Exception:
            pass

        try:
            from telethon.tl.types import PeerChannel
            cid = abs(num_id)
            if str(cid).startswith("100") and len(str(cid)) > 10:
                cid = int(str(cid)[3:])
            return await client.get_entity(PeerChannel(cid))
        except Exception:
            pass

    return await client.get_entity(target_str)


async def importar_catalogo(
    input_file: str,
    destino_chat: Any = None,
    source_chat: int = DEFAULT_SOURCE_CHAT,
    limit_series: Optional[int] = None,
    dry_run: bool = False
):
    # Auto-detección si no se especificó destino
    if not destino_chat:
        fn = os.path.basename(input_file).replace(".json", "")
        if "turca" in fn or "telenovela" in fn:
            destino_chat = "turcas_y_telenovelas"
        elif "espanola" in fn:
            destino_chat = "espanolas"
        elif "retro" in fn or "clasica" in fn:
            destino_chat = "retro_clasicas"
        elif "internacional" in fn:
            destino_chat = "internacionales"

    logger.info("=" * 70)
    logger.info("🚀 INICIANDO IMPORTACIÓN DE SERIES A SUPERGRUPO DE TELEGRAM")
    logger.info(f"Catálogo origen: {input_file}")
    logger.info(f"Destino: {destino_chat}")
    logger.info("=" * 70)

    if not os.path.exists(input_file):
        logger.error(f"❌ Archivo no encontrado: {input_file}")
        return

    with open(input_file, "r", encoding="utf-8") as f:
        catalogo = json.load(f)

    series_dict = catalogo.get("series", {})
    total_series = len(series_dict)
    logger.info(f"Total de series en el archivo: {total_series}")

    progress = load_progress()
    completed_set = set(progress.get("completed_series", {}).get(input_file, []))
    logger.info(f"Series ya completadas previamente en este archivo: {len(completed_set)}")

    series_pendientes = [
        (sname, sdata) for sname, sdata in series_dict.items()
        if sname not in completed_set
    ]

    if limit_series:
        series_pendientes = series_pendientes[:limit_series]
        logger.info(f"Límite aplicado: se procesarán {len(series_pendientes)} series en esta ejecución.")
    else:
        logger.info(f"Series pendientes a importar: {len(series_pendientes)}")

    if not series_pendientes:
        logger.info("🎉 ¡Todas las series de este catálogo ya han sido importadas!")
        return

    if not STRING_SESSION:
        logger.error("❌ TELEGRAM_STRING_SESSION no configurada.")
        return

    async with TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH) as client:
        # Resolver entidades
        try:
            dest_entity = await resolve_entity_robust(client, destino_chat)
            dest_input = await client.get_input_entity(dest_entity)
            source_entity = await resolve_entity_robust(client, source_chat)
            source_input = await client.get_input_entity(source_entity)
            dest_title = getattr(dest_entity, "title", str(destino_chat))
            logger.info(f"Conexión exitosa. Supergrupo destino: '{dest_title}'")
        except Exception as e:
            logger.error(f"Error resolviendo entidades de Telegram: {e}")
            return

        if dry_run:
            logger.info("🛑 Modo Dry-Run activo: no se crearán temas ni se reenviarán mensajes.")
            for i, (sname, sdata) in enumerate(series_pendientes[:15], 1):
                caps = sdata.get("total_capitulos", len(sdata.get("capitulos", [])))
                temps = sdata.get("temporadas", [])
                logger.info(f"  {i}. {sname} -> {caps} caps (T{temps})")
            return

        # Consultar temas existentes
        topics_map = await get_existing_forum_topics(client, dest_entity)

        # Procesar series secuencialmente
        for idx, (series_name, series_data) in enumerate(series_pendientes, 1):
            logger.info("-" * 60)
            logger.info(f"[{idx}/{len(series_pendientes)}] Procesando serie: '{series_name}'...")

            # 1. Obtener o crear Topic para la serie
            topic_id = await get_or_create_topic(client, dest_entity, series_name, topics_map)
            if not topic_id:
                logger.warning(f"Omitiendo serie '{series_name}' por no poder crear/encontrar tema.")
                continue

            # 2. Ordenar episodios cronológica y naturalmente por temporada y capítulo
            raw_caps = series_data.get("capitulos", [])
            sorted_caps = sorted(
                raw_caps,
                key=lambda x: (x.get("season", 1), x.get("episode", 1), x.get("message_id", 0))
            )
            msg_ids = [c["message_id"] for c in sorted_caps]
            logger.info(f"Reenviando {len(msg_ids)} episodios ordenados hacia el tema '{series_name}' (ID {topic_id})...")

            # 3. Reenviar en lotes de 10 mensajes usando ForwardMessagesRequest con top_msg_id
            lote_tamano = 10
            for i in range(0, len(msg_ids), lote_tamano):
                chunk = msg_ids[i:i + lote_tamano]
                rand_ids = [random.randint(1, 2**63 - 1) for _ in chunk]
                success = False

                while not success:
                    try:
                        await client(ForwardMessagesRequest(
                            from_peer=source_input,
                            to_peer=dest_input,
                            id=chunk,
                            random_id=rand_ids,
                            drop_author=True,
                            top_msg_id=topic_id
                        ))
                        success = True
                        await asyncio.sleep(1.8)

                    except errors.FloodWaitError as e:
                        logger.warning(f"FloodWait al reenviar: esperando {e.seconds + 2}s...")
                        await asyncio.sleep(e.seconds + 2)

                    except Exception as ex_lote:
                        logger.warning(f"Fallo en lote ({ex_lote}). Intentando reenvío individual...")
                        for single_id in chunk:
                            try:
                                await client(ForwardMessagesRequest(
                                    from_peer=source_input,
                                    to_peer=dest_input,
                                    id=[single_id],
                                    random_id=[random.randint(1, 2**63 - 1)],
                                    drop_author=True,
                                    top_msg_id=topic_id
                                ))
                                await asyncio.sleep(1.8)
                            except Exception as ex_single:
                                logger.error(f"No se pudo reenviar mensaje {single_id}: {ex_single}")
                        success = True

            # 4. Registrar en checkpoint de progreso
            completed_set.add(series_name)
            progress.setdefault("completed_series", {})[input_file] = list(completed_set)
            save_progress(progress)
            logger.info(f"✅ Serie '{series_name}' completada ({len(msg_ids)} caps). Checkpoint actualizado.")

    # 5. Comprobar si restan más series por importar para auto-encadenamiento
    pendientes_restantes = [s for s in series_dict.keys() if s not in completed_set]
    if pendientes_restantes:
        logger.info(f"ℹ️ Quedan {len(pendientes_restantes)} series pendientes en este catálogo.")
        try:
            with open(".more_series", "w", encoding="utf-8") as f:
                f.write(str(len(pendientes_restantes)))
        except Exception as e:
            logger.warning(f"No se pudo escribir .more_series: {e}")
    else:
        logger.info("🎉 ¡Todas las series del catálogo han sido importadas con éxito!")
        if os.path.exists(".more_series"):
            try:
                os.remove(".more_series")
            except Exception:
                pass

    logger.info("=" * 70)
    logger.info("🎉 ¡PROCESO DE IMPORTACIÓN FINALIZADO CON ÉXITO!")
    logger.info("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Importador masivo de series hacia supergrupos de Telegram con Foros.")
    parser.add_argument("--input", required=True, help="Archivo JSON del catálogo a importar (ej. series_turcas_y_telenovelas.json)")
    parser.add_argument("--destino", required=False, default=None, help="ID numérico, alias o enlace de invitación del Supergrupo destino")
    parser.add_argument("--source-chat", type=int, default=DEFAULT_SOURCE_CHAT, help="ID del canal origen de los videos")
    parser.add_argument("--limit-series", type=int, default=None, help="Límite de series a procesar en esta tanda")
    parser.add_argument("--dry-run", action="store_true", help="Simulación sin modificar Telegram")

    args = parser.parse_args()

    dest = None
    if args.destino:
        dest = args.destino.strip(" '\"")
        if re.match(r"^-?\d+$", dest):
            dest = int(dest)

    asyncio.run(importar_catalogo(
        input_file=args.input,
        destino_chat=dest,
        source_chat=args.source_chat,
        limit_series=args.limit_series,
        dry_run=args.dry_run
    ))


if __name__ == "__main__":
    main()
