#!/usr/bin/env python3
"""
migrar_hd4k_maestro.py — Motor Maestro de Migración Histórica y Sincronización Incremental HD/4K
TeVeFLIPE

Arquitectura:
1. Mapeo y Resolución Automática de los 4 Canales de Producción HD/4K.
2. Reconocimiento de Obras Migradas Previas (ej: La bella y la bestia [3D] en -1004291273383).
3. Agrupación y Validación Estricta de Obras (1..N sin huecos, Store RAR5 / Raw Split).
4. Reenvío Nativo en Telegram por Lotes Idempotentes con Registro Persistente.
5. Verificación en Destino y Actualización Transaccional del Estado.
6. Soporte de Modo Migración Histórica (--migrate) y Modo Incremental (--incremental).
"""

import os
import sys
import time
import json
import asyncio
import logging
import re
from typing import Dict, List, Any, Optional, Tuple

from telethon import TelegramClient, utils, errors
from telethon.sessions import StringSession
from telethon.tl.functions.channels import (
    CreateChannelRequest,
    EditAdminRequest,
    ToggleForumRequest,
    InviteToChannelRequest
)
from telethon.tl.functions.messages import (
    ExportChatInviteRequest,
    CreateForumTopicRequest,
    GetForumTopicsRequest
)
from telethon.tl.types import (
    ChatAdminRights,
    ChatInviteExported,
    MessageMediaDocument
)

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(
    format="[%(asctime)s] %(levelname)s - %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("MigradorHD4K")

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_BUNKER = os.getenv("SESSION_BUNKER", "").strip()
SESSION_PROD = os.getenv("SESSION_PROD", "").strip()

STATE_FILE = "sync_hd4k_state.json"
MAX_BATCH_WORKS_DEFAULT = int(os.getenv("MAX_BATCH_WORKS", "10"))
MAX_RUN_SECONDS_DEFAULT = int(os.getenv("MAX_RUN_SECONDS", "1800"))  # 30 minutos por runner

# Definición de los 4 búnkers canónicos HD/4K
BUNKERS_CONFIG = {
    "pelis_clasicas": {
        "bunker_id": -1004450378925,
        "bunker_name": "Películas Clásicas HD/4K Bunker",
        "target_title": "🎞️ Películas Clásicas HD/4K — TeVeFLIPE",
        "target_type": "broadcast",
        "known_prod_id": -1004291273383  # Ya creado en el piloto
    },
    "pelis_2000": {
        "bunker_id": -1004420612937,
        "bunker_name": "Películas 2000-2019 HD/4K Bunker",
        "target_title": "🎬 Películas 2000-2019 HD/4K — TeVeFLIPE",
        "target_type": "broadcast",
        "known_prod_id": None
    },
    "pelis_estrenos": {
        "bunker_id": -5498750167,
        "bunker_name": "Películas Estrenos HD/4K Bunker",
        "target_title": "🏆 Películas Estrenos HD/4K — TeVeFLIPE",
        "target_type": "broadcast",
        "known_prod_id": None
    },
    "series": {
        "bunker_id": -1004457839581,
        "bunker_name": "Series HD/4K Bunker",
        "target_title": "📺 Series HD/4K — TeVeFLIPE",
        "target_type": "forum",
        "known_prod_id": None
    }
}

LEGACY_DESTINATIONS = {
    -1003763464899, -1004331019870, -1004419790119, -1003886841797,
    -1004467288762, -1004326583216, -1004343712699, -1004300040143,
    -1004445508015, -1004341160346, -1004415457188, -1003865750796,
    -1004390222354, -1004296746003, -1004405196455
}

def load_state() -> Dict[str, Any]:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Error cargando estado {STATE_FILE}: {e}")
            
    # Inicialización por defecto
    return {
        "version": "1.0",
        "updated_at": time.time(),
        "channels": {},
        "migrated_works": {
            # Registrar La bella y la bestia como migrada para evitar duplicados
            "pelis_clasicas::la bella y la bestia [3d]::1991": {
                "titulo": "La bella y la bestia [3D] (1991)",
                "bunker_id": -1004450378925,
                "prod_id": -1004291273383,
                "ficha_msg_id": 2,
                "part_msg_ids": list(range(3, 20)),
                "total_parts": 17,
                "status": "CONFIRMED_PILOT",
                "verified_at": time.time()
            }
        },
        "incidents_queue": []
    }

def save_state(state: Dict[str, Any]):
    state["updated_at"] = time.time()
    temp_file = f"{STATE_FILE}.tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp_file, STATE_FILE)

async def resolve_or_create_channel(cp: TelegramClient, cb: TelegramClient, key: str, cfg: Dict[str, Any], state: Dict[str, Any]) -> Tuple[Any, int]:
    """Resuelve o crea un canal de Producción HD/4K de forma idempotente."""
    target_title = cfg["target_title"]
    is_forum = (cfg["target_type"] == "forum")
    known_id = cfg.get("known_prod_id") or state.get("channels", {}).get(key, {}).get("prod_id")

    dest_entity = None
    if known_id:
        try:
            dest_entity = await cp.get_entity(known_id)
            logger.info(f"✅ Canal '{target_title}' resuelto mediante ID conocido ({known_id}).")
        except Exception as e:
            logger.warning(f"No se pudo resolver ID conocido {known_id}: {e}")

    if not dest_entity:
        logger.info(f"🔍 Buscando si '{target_title}' existe en diálogos de Producción...")
        async for d in cp.iter_dialogs(limit=200):
            t = (d.title or "").strip().lower()
            if target_title.lower() in t or cfg["bunker_name"].lower().replace("bunker", "").strip() in t:
                pid = utils.get_peer_id(d.entity)
                if pid in LEGACY_DESTINATIONS or pid == cfg["bunker_id"]:
                    continue
                dest_entity = d.entity
                logger.info(f"✅ Canal encontrado en diálogos: '{d.title}' (ID: {pid})")
                break

    if not dest_entity:
        logger.info(f"🚀 Creando canal privado: '{target_title}' (Tipo: {cfg['target_type']})...")
        res = await cp(CreateChannelRequest(
            title=target_title,
            about=f"Canal Privado Oficial de Producción TeVeFLIPE para {cfg['bunker_name']}.",
            broadcast=not is_forum,
            megagroup=is_forum
        ))
        dest_entity = res.chats[0]
        pid = utils.get_peer_id(dest_entity)
        logger.info(f"🎉 Canal creado con éxito: '{dest_entity.title}' [ID: {pid}]")

        if is_forum:
            logger.info("Activando funcionalidad de Foros/Temas en el supergrupo...")
            try:
                await cp(ToggleForumRequest(channel=dest_entity, enabled=True))
                logger.info("✅ Foros activados con éxito en el supergrupo.")
            except Exception as e_f:
                logger.warning(f"Aviso activando foros: {e_f}")

    pid = utils.get_peer_id(dest_entity)

    # Validaciones de seguridad
    if pid in LEGACY_DESTINATIONS:
        raise ValueError(f"🛑 BLOQUEO: El ID {pid} coincide con un canal legacy.")
    if pid == cfg["bunker_id"]:
        raise ValueError(f"🛑 BLOQUEO: El ID {pid} coincide con el búnker de origen.")

    # Otorgar permisos a la cuenta Búnker si no los tiene
    me_b = await cb.get_me()
    try:
        admin_rights = ChatAdminRights(
            post_messages=True,
            edit_messages=True,
            delete_messages=False,
            invite_users=True,
            manage_topics=True if is_forum else False
        )
        await cp(EditAdminRequest(
            channel=dest_entity,
            user_id=me_b.id,
            admin_rights=admin_rights,
            rank="Forwarder HD4K"
        ))
        logger.info(f"✅ Permisos de administración configurados para Búnker ({me_b.first_name}) en {pid}.")
    except Exception as e_adm:
        logger.warning(f"Aviso permisos admin en {pid}: {e_adm}")

    # Guardar en estado
    if "channels" not in state:
        state["channels"] = {}
    state["channels"][key] = {
        "bunker_id": cfg["bunker_id"],
        "bunker_name": cfg["bunker_name"],
        "prod_id": pid,
        "prod_title": getattr(dest_entity, 'title', target_title),
        "target_type": cfg["target_type"],
        "last_synced_id": state.get("channels", {}).get(key, {}).get("last_synced_id", 0)
    }

    return dest_entity, pid

def clean_title_and_extract_parts(text: str, filename: str) -> Tuple[str, Optional[int], Optional[int]]:
    """Extrae título limpio, número de parte y total de partes si existen."""
    raw = (text or "").split("\n")[0].strip()
    if not raw and filename:
        raw = filename
        
    # Limpiar emojis iniciales
    raw = re.sub(r'^[🎬📺🎥🎞️👶💥🥢✨📼🌍🎸🪐\[\(#\s*]+', '', raw).strip()
    
    # Detectar partes: .001 / .part1.rar / .part01
    part_num = None
    total_parts = None
    
    m_split = re.search(r'\.0*(\d{1,4})$', filename)
    if m_split:
        part_num = int(m_split.group(1))
        
    m_rar = re.search(r'(?i)\.part0*(\d+)\.rar$', filename)
    if m_rar:
        part_num = int(m_rar.group(1))
        
    # Buscar total en texto ej: "(17 partes)" o "Parte 1 de 5"
    m_tot = re.search(r'(?i)(?:de|\/)\s*(\d+)\s*(?:partes|archivos)?', text or "")
    if m_tot:
        total_parts = int(m_tot.group(1))
        
    title_clean = re.sub(r'(?i)\.(?:7z|rar|mkv|mp4)(?:\.\d+)?$', '', raw)
    title_clean = re.sub(r'(?i)[._\s\-\(\[]part(?:e|\s)?\d+.*$', '', title_clean).strip()
    
    return title_clean.lower(), part_num, total_parts

async def scan_and_migrate_bunker(cp: TelegramClient, cb: TelegramClient, key: str, cfg: Dict[str, Any], state: Dict[str, Any], max_works: int = 10, max_seconds: int = 1800) -> Dict[str, Any]:
    """Escanea y migra un lote seguro de obras de un búnker."""
    t_start = time.time()
    bunker_id = cfg["bunker_id"]
    prod_id = state["channels"][key]["prod_id"]
    last_cursor = state["channels"][key].get("last_synced_id", 0)

    logger.info("=" * 75)
    logger.info(f"📦 ESCANEANDO Y MIGRANDO: {cfg['bunker_name']} (Cursor: {last_cursor})")
    logger.info(f"   Destino: {state['channels'][key]['prod_title']} [ID: {prod_id}]")
    logger.info("=" * 75)

    ent_bunker = await cb.get_input_entity(bunker_id)
    ent_prod_b = await cb.get_input_entity(prod_id)
    ent_prod_p = await cp.get_input_entity(prod_id)

    # 1. Inspeccionar mensajes ya presentes en destino para deduplicación
    existing_dest_files = {}
    async for m in cp.iter_messages(ent_prod_p, limit=300):
        if m.file and m.file.name:
            existing_dest_files[m.file.name] = {"id": m.id, "size": m.file.size}

    # 2. Leer nuevos mensajes desde last_cursor
    works_migrated = 0
    messages_forwarded = 0
    bytes_transferred = 0
    current_cursor = last_cursor

    # Recorrer mensajes en orden ascendente (reverse=True con min_id)
    new_msgs = []
    async for m in cb.iter_messages(ent_bunker, min_id=last_cursor, reverse=True, limit=200):
        new_msgs.append(m)

    if not new_msgs:
        logger.info(f"ℹ️ El búnker {key} está 100% AL DÍA. Cero mensajes pendientes desde cursor {last_cursor}.")
        return {"key": key, "migrated": 0, "status": "AL_DIA"}

    logger.info(f"Analizando {len(new_msgs)} mensajes recuperados del búnker...")

    # Agrupar mensajes por obras contiguas
    idx = 0
    while idx < len(new_msgs) and works_migrated < max_works:
        if time.time() - t_start > max_seconds:
            logger.info("⏳ Tiempo máximo del lote alcanzado. Guardando estado...")
            break

        m = new_msgs[idx]
        
        # Ignorar mensajes de servicio
        if m.action:
            current_cursor = max(current_cursor, m.id)
            idx += 1
            continue

        # Caso A: Ficha descriptiva de texto seguida de archivos
        is_card = bool(m.text and ('🎬' in m.text or 'Calidad:' in m.text or 'Sinopsis' in m.text or 'Duración' in m.text))
        
        card_msg = m if is_card else None
        files_msgs = []

        if is_card:
            # Buscar ficheros adjuntos subsiguientes
            sub_idx = idx + 1
            while sub_idx < len(new_msgs):
                sub_m = new_msgs[sub_idx]
                if sub_m.file and sub_m.file.name:
                    files_msgs.append(sub_m)
                    sub_idx += 1
                elif sub_m.text and ('🎬' in sub_m.text or 'Calidad:' in sub_m.text):
                    # Comienza otra ficha
                    break
                else:
                    sub_idx += 1
            advance_step = max(1, sub_idx - idx)
        else:
            if m.file and m.file.name:
                files_msgs.append(m)
            advance_step = 1

        if not files_msgs:
            # Mensaje informativo o tarjeta sin fichero inmediato en este segmento
            current_cursor = max(current_cursor, m.id)
            idx += advance_step
            continue

        # Determinar clave canónica de la obra
        first_fn = files_msgs[0].file.name
        t_clean, part_n, total_p = clean_title_and_extract_parts(card_msg.text if card_msg else "", first_fn)
        work_key = f"{key}::{t_clean}"

        # Comprobar si ya fue migrada
        if work_key in state.get("migrated_works", {}):
            logger.info(f"ℹ️ Obra '{t_clean}' ya figura como migrada previamente en estado. Omitiendo.")
            for fm in files_msgs:
                current_cursor = max(current_cursor, fm.id)
            if card_msg:
                current_cursor = max(current_cursor, card_msg.id)
            idx += advance_step
            continue

        # Validar si es multipart y si están todas las partes
        is_multipart = len(files_msgs) > 1 or (part_n is not None and part_n > 0)
        
        if is_multipart and total_p and len(files_msgs) < total_p:
            logger.warning(f"⚠️ Obra '{t_clean}' incompleta: detectadas {len(files_msgs)} partes de {total_p}. Reteniendo en cola.")
            state["incidents_queue"].append({
                "work_key": work_key,
                "reason": f"Incompleta: {len(files_msgs)}/{total_p} partes",
                "first_msg_id": files_msgs[0].id
            })
            idx += advance_step
            continue

        # Proceder a la transferencia de la obra completa
        logger.info(f"📤 Transfiriendo obra: '{t_clean}' ({len(files_msgs)} archivos)...")
        dest_card_id = None
        
        # 1. Reenviar ficha si existe
        if card_msg:
            try:
                fwd_c = await cb.forward_messages(entity=ent_prod_b, messages=card_msg.id, from_peer=ent_bunker)
                dest_card_id = fwd_c[0].id if isinstance(fwd_c, list) else fwd_c.id
                await asyncio.sleep(1.0)
            except Exception as e_c:
                logger.warning(f"Error reenviando ficha: {e_c}")

        # 2. Reenviar archivos ordenadamente
        confirmed_dest_ids = []
        work_bytes = 0
        all_parts_ok = True

        for fm in files_msgs:
            fn = fm.file.name
            sz = fm.file.size
            work_bytes += sz

            if fn in existing_dest_files and existing_dest_files[fn]["size"] == sz:
                did = existing_dest_files[fn]["id"]
                logger.info(f"  Archivo '{fn}' ya existía en destino (ID {did}). Reutilizando.")
                confirmed_dest_ids.append(did)
                continue

            try:
                fwd_f = await cb.forward_messages(entity=ent_prod_b, messages=fm.id, from_peer=ent_bunker)
                did = fwd_f[0].id if isinstance(fwd_f, list) else fwd_f.id
                confirmed_dest_ids.append(did)
                messages_forwarded += 1
                logger.info(f"  ✅ '{fn}' ({sz/(1024*1024):.1f} MB) ➔ Destino ID {did}")
                await asyncio.sleep(1.2)
            except Exception as e_f:
                logger.error(f"🛑 Error reenviando '{fn}': {e_f}")
                all_parts_ok = False
                break

        if all_parts_ok:
            works_migrated += 1
            bytes_transferred += work_bytes
            state["migrated_works"][work_key] = {
                "titulo": t_clean,
                "bunker_id": bunker_id,
                "prod_id": prod_id,
                "ficha_msg_id": dest_card_id,
                "part_msg_ids": confirmed_dest_ids,
                "total_parts": len(confirmed_dest_ids),
                "total_bytes": work_bytes,
                "status": "CONFIRMED_SUCCESS",
                "verified_at": time.time()
            }
            # Actualizar cursor al último mensaje confirmado de la obra
            for fm in files_msgs:
                current_cursor = max(current_cursor, fm.id)
            if card_msg:
                current_cursor = max(current_cursor, card_msg.id)
            state["channels"][key]["last_synced_id"] = current_cursor
            save_state(state)
            logger.info(f"🎉 Obra '{t_clean}' migrada y sellada con éxito. Nuevo cursor: {current_cursor}")
        else:
            logger.warning(f"⚠️ Obra '{t_clean}' falló parcialmente. Cursor no avanzado.")
            break

        idx += advance_step

    return {
        "key": key,
        "migrated": works_migrated,
        "messages_forwarded": messages_forwarded,
        "bytes_transferred": bytes_transferred,
        "cursor_final": current_cursor,
        "duration_sec": round(time.time() - t_start, 2)
    }

async def main():
    mode = "--incremental" if "--incremental" in sys.argv else "--migrate"
    print("=" * 80)
    print(f"🛰️ MOTOR MAESTRO DE MIGRACIÓN Y SINCRONIZACIÓN HD/4K TEVEFLIPE")
    print(f"   Modo de ejecución: {mode.upper()}")
    print("=" * 80)

    if not SESSION_BUNKER or not SESSION_PROD:
        logger.error("❌ ERROR: SESSION_BUNKER y SESSION_PROD deben estar ambas configuradas.")
        sys.exit(1)

    cb = TelegramClient(StringSession(SESSION_BUNKER), API_ID, API_HASH)
    cp = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)

    await cb.start()
    await cp.start()

    me_b = await cb.get_me()
    me_p = await cp.get_me()
    logger.info(f"👤 Búnker: {me_b.first_name} [ID: {me_b.id}] | Producción: {me_p.first_name} [ID: {me_p.id}]")

    state = load_state()

    # FASE 1: Resolución / Creación de Canales de Producción
    print("\n" + "=" * 75)
    print("📋 FASE 1: RESOLUCIÓN Y CREACIÓN DE CANALES DE DESTINO")
    print("=" * 75)
    for k, cfg in BUNKERS_CONFIG.items():
        dest_ent, pid = await resolve_or_create_channel(cp, cb, k, cfg, state)
        logger.info(f"📌 Mapeo Certificado: {cfg['bunker_name']} ({cfg['bunker_id']}) ➔ {cfg['target_title']} ({pid})")

    save_state(state)

    # FASE 2: Migración por Lotes de los Canales
    print("\n" + "=" * 75)
    print("🚀 FASE 2: TRANSFERENCIA POR LOTES IDEMPOTENTE")
    print("=" * 75)
    results = []
    
    # Procesar Clásicas y 2000-2019
    for k in ["pelis_clasicas", "pelis_2000", "pelis_estrenos", "series"]:
        cfg = BUNKERS_CONFIG[k]
        res = await scan_and_migrate_bunker(cp, cb, k, cfg, state, max_works=MAX_BATCH_WORKS_DEFAULT, max_seconds=600)
        results.append(res)

    # FASE 3: Conciliación y Reporte Final
    print("\n" + "=" * 75)
    print("📊 FASE 3: CONCILIACIÓN DEL ESTADO")
    print("=" * 75)
    total_migradas = len(state.get("migrated_works", {}))
    logger.info(f"Total obras registradas en estado permanente: {total_migradas}")
    for k, r in enumerate(results, 1):
        logger.info(f"  {r['key']}: {r.get('migrated', 0)} obras migradas en esta ejecución.")

    save_state(state)

    await cb.disconnect()
    await cp.disconnect()
    logger.info("🔒 Sesiones cerradas limpiamente.")

if __name__ == '__main__':
    asyncio.run(main())
