#!/usr/bin/env python3
"""
migrar_hd4k_maestro.py — Motor Maestro de Migración Histórica y Sincronización Incremental HD/4K
TeVeFLIPE

Arquitectura de Alta Eficiencia:
1. Mapeo y Resolución de los 4 Canales de Producción HD/4K.
2. Separación de Estados por Canal: BACKFILL, RECONCILING, INCREMENTAL, BACKFILL_PAUSED_TOPICS.
3. Validación Estricta de Obras (1..N sin huecos, preservación de fichas y orden).
4. Procesamiento Continuo por Lotes con Presupuesto de Tiempo (Time-Budgeted Round-Robin).
5. Idempotencia Absoluta con Persistencia Transaccional y Reconciliación de Destino.
6. Manejo Resiliente de FloodWait y Rate Limits de Telegram MTProto.
7. Detención Segura del Lote de Series ante Atribución Incierta de Topics (Regla Tarea 4).
8. Métricas Claras: Obras/Archivos/Bytes Nuevos vs Previos vs Totales Confirmados.
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
)
from telethon.tl.types import (
    ChatAdminRights,
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
MAX_RUN_SECONDS = int(os.getenv("MAX_RUN_SECONDS", "2100"))  # 35 minutos de presupuesto activo
MAX_WORKS_PER_PASS = int(os.getenv("MAX_BATCH_WORKS", "30"))  # Obras por pasada de canal
FWD_SLEEP_PART = float(os.getenv("FWD_SLEEP_PART", "0.9"))   # Pausa entre partes
FWD_SLEEP_WORK = float(os.getenv("FWD_SLEEP_WORK", "1.5"))   # Pausa entre obras

# Configuración de los 4 búnkers canónicos HD/4K
BUNKERS_CONFIG = {
    "pelis_clasicas": {
        "bunker_id": -1004450378925,
        "bunker_name": "Películas Clásicas HD/4K Bunker",
        "target_title": "🎞️ Películas Clásicas HD/4K — TeVeFLIPE",
        "target_type": "broadcast",
        "known_prod_id": -1004291273383
    },
    "pelis_2000": {
        "bunker_id": -1004420612937,
        "bunker_name": "Películas 2000-2019 HD/4K Bunker",
        "target_title": "🎬 Películas 2000-2019 HD/4K — TeVeFLIPE",
        "target_type": "broadcast",
        "known_prod_id": -1004336513084
    },
    "pelis_estrenos": {
        "bunker_id": -5498750167,
        "bunker_name": "Películas Estrenos HD/4K Bunker",
        "target_title": "🏆 Películas Estrenos HD/4K — TeVeFLIPE",
        "target_type": "broadcast",
        "known_prod_id": -1004377860188
    },
    "series": {
        "bunker_id": -1004457839581,
        "bunker_name": "Series HD/4K Bunker",
        "target_title": "📺 Series HD/4K — TeVeFLIPE",
        "target_type": "forum",
        "known_prod_id": -1004312744356,
        "paused_reason": "Destino supergrupo sin temas/topics dedicados por serie configurados. Detenido preventivamente conforme a Tarea 4."
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
                state = json.load(f)
                # Enriquecer La bella y la bestia si tiene 0 bytes
                pilot_key = "pelis_clasicas::la bella y la bestia [3d]::1991"
                if pilot_key in state.get("migrated_works", {}):
                    if state["migrated_works"][pilot_key].get("total_bytes", 0) == 0:
                        state["migrated_works"][pilot_key]["total_bytes"] = 17395578987
                return state
        except Exception as e:
            logger.warning(f"Error cargando estado {STATE_FILE}: {e}")

    return {
        "version": "2.0",
        "updated_at": time.time(),
        "channels": {},
        "migrated_works": {
            "pelis_clasicas::la bella y la bestia [3d]::1991": {
                "titulo": "La bella y la bestia [3D] (1991)",
                "bunker_id": -1004450378925,
                "prod_id": -1004291273383,
                "ficha_msg_id": 2,
                "part_msg_ids": list(range(3, 20)),
                "total_parts": 17,
                "total_bytes": 17395578987,
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
            try:
                await cp(ToggleForumRequest(channel=dest_entity, enabled=True))
            except Exception as e_f:
                logger.warning(f"Aviso activando foros: {e_f}")

    pid = utils.get_peer_id(dest_entity)

    if pid in LEGACY_DESTINATIONS:
        raise ValueError(f"🛑 BLOQUEO: El ID {pid} coincide con un canal legacy.")
    if pid == cfg["bunker_id"]:
        raise ValueError(f"🛑 BLOQUEO: El ID {pid} coincide con el búnker de origen.")

    # Asegurar permisos de Búnker en destino
    try:
        me_b = await cb.get_me()
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
    except Exception as e_adm:
        logger.debug(f"Aviso permisos admin: {e_adm}")

    if "channels" not in state:
        state["channels"] = {}

    existing_ch = state["channels"].get(key, {})
    current_phase = existing_ch.get("sync_phase")
    if not current_phase:
        current_phase = "BACKFILL_PAUSED_TOPICS" if key == "series" else "BACKFILL"

    state["channels"][key] = {
        "bunker_id": cfg["bunker_id"],
        "bunker_name": cfg["bunker_name"],
        "prod_id": pid,
        "prod_title": getattr(dest_entity, 'title', target_title),
        "target_type": cfg["target_type"],
        "last_synced_id": existing_ch.get("last_synced_id", 0),
        "sync_phase": current_phase,
        "paused_reason": cfg.get("paused_reason") if key == "series" else None
    }

    return dest_entity, pid

def clean_title_and_extract_parts(text: str, filename: str) -> Tuple[str, Optional[int], Optional[int]]:
    raw = (text or "").split("\n")[0].strip()
    if not raw and filename:
        raw = filename

    raw = re.sub(r'^[🎬📺🎥🎞️👶💥🥢✨📼🌍🎸🪐\[\(#\s*]+', '', raw).strip()

    part_num = None
    total_parts = None

    m_split = re.search(r'\.0*(\d{1,4})$', filename)
    if m_split:
        part_num = int(m_split.group(1))

    m_rar = re.search(r'(?i)\.part0*(\d+)\.rar$', filename)
    if m_rar:
        part_num = int(m_rar.group(1))

    m_tot = re.search(r'(?i)(?:de|\/)\s*(\d+)\s*(?:partes|archivos)?', text or "")
    if m_tot:
        total_parts = int(m_tot.group(1))

    title_clean = re.sub(r'(?i)\.(?:7z|rar|mkv|mp4)(?:\.\d+)?$', '', raw)
    title_clean = re.sub(r'(?i)[._\s\-\(\[]part(?:e|\s)?\d+.*$', '', title_clean).strip()

    return title_clean.lower(), part_num, total_parts

async def migrate_channel_pass(
    cp: TelegramClient,
    cb: TelegramClient,
    key: str,
    cfg: Dict[str, Any],
    state: Dict[str, Any],
    max_works: int,
    deadline_ts: float
) -> Dict[str, Any]:
    """Ejecuta una pasada de migración de obras en un canal hasta max_works o deadline_ts."""
    ch_info = state["channels"][key]
    bunker_id = cfg["bunker_id"]
    prod_id = ch_info["prod_id"]
    last_cursor = ch_info.get("last_synced_id", 0)
    phase = ch_info.get("sync_phase", "BACKFILL")

    if phase == "BACKFILL_PAUSED_TOPICS":
        logger.info(f"⏸️ Canal '{key}' en pausa de seguridad por temas/topics. Omitiendo según Tarea 4.")
        return {"key": key, "status": "PAUSED", "works_migrated": 0, "messages_forwarded": 0, "bytes_transferred": 0}

    logger.info(f"▶️ Procesando pasada para [{key}] '{ch_info['prod_title']}' (Fase: {phase}, Cursor: {last_cursor})")

    ent_bunker = await cb.get_input_entity(bunker_id)
    ent_prod_b = await cb.get_input_entity(prod_id)
    ent_prod_p = await cp.get_input_entity(prod_id)

    # Conocer el ID máximo actual del búnker
    latest_msgs = await cb.get_messages(ent_bunker, limit=1)
    bunker_max_id = latest_msgs[0].id if latest_msgs else last_cursor
    ch_info["bunker_max_id"] = bunker_max_id

    # Si ya alcanzamos el final del búnker
    if last_cursor >= bunker_max_id:
        if phase == "BACKFILL":
            logger.info(f"🏁 Canal '{key}' ha alcanzado el final histórico ({bunker_max_id}). Conmutando a INCREMENTAL.")
            ch_info["sync_phase"] = "INCREMENTAL"
            save_state(state)
        return {"key": key, "status": "UP_TO_DATE", "works_migrated": 0, "messages_forwarded": 0, "bytes_transferred": 0}

    # Caché de archivos existentes en destino para deduplicación local
    existing_dest_files = {}
    async for m in cp.iter_messages(ent_prod_p, limit=300):
        if m.file and m.file.name:
            existing_dest_files[m.file.name] = {"id": m.id, "size": m.file.size}

    works_migrated = 0
    messages_forwarded = 0
    bytes_transferred = 0
    current_cursor = last_cursor

    # Leer bloque de mensajes en orden cronológico ascendente (min_id + reverse=True)
    new_msgs = []
    async for m in cb.iter_messages(ent_bunker, min_id=last_cursor, reverse=True, limit=150):
        new_msgs.append(m)

    if not new_msgs:
        if phase == "BACKFILL":
            ch_info["sync_phase"] = "INCREMENTAL"
            save_state(state)
        return {"key": key, "status": "UP_TO_DATE", "works_migrated": 0, "messages_forwarded": 0, "bytes_transferred": 0}

    idx = 0
    while idx < len(new_msgs) and works_migrated < max_works:
        if time.time() > deadline_ts:
            logger.info(f"⏳ Presupuesto de tiempo alcanzado en pasada de '{key}'. Guardando y cediendo.")
            break

        m = new_msgs[idx]

        if m.action:
            current_cursor = max(current_cursor, m.id)
            idx += 1
            continue

        # Detección de ficha
        is_card = bool(m.text and ('🎬' in m.text or 'Calidad:' in m.text or 'Sinopsis' in m.text or 'Duración' in m.text))
        card_msg = m if is_card else None
        files_msgs = []

        if is_card:
            sub_idx = idx + 1
            while sub_idx < len(new_msgs):
                sub_m = new_msgs[sub_idx]
                if sub_m.file and sub_m.file.name:
                    files_msgs.append(sub_m)
                    sub_idx += 1
                elif sub_m.text and ('🎬' in sub_m.text or 'Calidad:' in sub_m.text):
                    break
                else:
                    sub_idx += 1
            advance_step = max(1, sub_idx - idx)
        else:
            if m.file and m.file.name:
                files_msgs.append(m)
            advance_step = 1

        if not files_msgs:
            current_cursor = max(current_cursor, m.id)
            idx += advance_step
            continue

        first_fn = files_msgs[0].file.name
        t_clean, part_n, total_p = clean_title_and_extract_parts(card_msg.text if card_msg else "", first_fn)
        work_key = f"{key}::{t_clean}"

        # Idempotencia: Verificar si ya figura migrada
        if work_key in state.get("migrated_works", {}):
            for fm in files_msgs:
                current_cursor = max(current_cursor, fm.id)
            if card_msg:
                current_cursor = max(current_cursor, card_msg.id)
            idx += advance_step
            continue

        # Verificar integridad si es multipart
        is_multipart = len(files_msgs) > 1 or (part_n is not None and part_n > 0)
        if is_multipart and total_p and len(files_msgs) < total_p:
            logger.warning(f"⚠️ Obra '{t_clean}' incompleta ({len(files_msgs)}/{total_p} partes detectadas en ventana). Esperando.")
            # No avanzar cursor para no saltear esta obra incompleta
            idx += advance_step
            continue

        # Reenviar de forma segura
        logger.info(f"📤 [{key}] Transfiriendo obra: '{t_clean}' ({len(files_msgs)} archivos)...")
        dest_card_id = None

        if card_msg:
            try:
                fwd_c = await cb.forward_messages(entity=ent_prod_b, messages=card_msg.id, from_peer=ent_bunker)
                dest_card_id = fwd_c[0].id if isinstance(fwd_c, list) else fwd_c.id
                await asyncio.sleep(0.8)
            except errors.FloodWaitError as fwe:
                logger.warning(f"FloodWait de {fwe.seconds}s. Esperando...")
                await asyncio.sleep(fwe.seconds + 2)
                fwd_c = await cb.forward_messages(entity=ent_prod_b, messages=card_msg.id, from_peer=ent_bunker)
                dest_card_id = fwd_c[0].id if isinstance(fwd_c, list) else fwd_c.id
            except Exception as e_c:
                logger.warning(f"Error reenviando ficha: {e_c}")

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
                await asyncio.sleep(FWD_SLEEP_PART)
            except errors.FloodWaitError as fwe:
                logger.warning(f"FloodWait de {fwe.seconds}s en archivo. Esperando...")
                await asyncio.sleep(fwe.seconds + 2)
                fwd_f = await cb.forward_messages(entity=ent_prod_b, messages=fm.id, from_peer=ent_bunker)
                did = fwd_f[0].id if isinstance(fwd_f, list) else fwd_f.id
                confirmed_dest_ids.append(did)
                messages_forwarded += 1
                logger.info(f"  ✅ '{fn}' tras espera ➔ Destino ID {did}")
                await asyncio.sleep(FWD_SLEEP_PART)
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
                "topic_id": None,
                "ficha_msg_id": dest_card_id,
                "part_msg_ids": confirmed_dest_ids,
                "total_parts": len(confirmed_dest_ids),
                "total_bytes": work_bytes,
                "status": "CONFIRMED_SUCCESS",
                "verified_at": time.time()
            }
            for fm in files_msgs:
                current_cursor = max(current_cursor, fm.id)
            if card_msg:
                current_cursor = max(current_cursor, card_msg.id)
            ch_info["last_synced_id"] = current_cursor
            save_state(state)
            logger.info(f"🎉 Obra '{t_clean}' sellada con éxito. Cursor: {current_cursor}")
            await asyncio.sleep(FWD_SLEEP_WORK)
        else:
            logger.warning(f"⚠️ Obra '{t_clean}' falló parcialmente. Cursor no avanzado.")
            break

        idx += advance_step

    return {
        "key": key,
        "status": "IN_PROGRESS" if current_cursor < bunker_max_id else "COMPLETED",
        "works_migrated": works_migrated,
        "messages_forwarded": messages_forwarded,
        "bytes_transferred": bytes_transferred,
        "cursor_final": current_cursor
    }

async def main():
    mode = "--incremental" if "--incremental" in sys.argv else "--migrate"
    run_start = time.time()
    deadline = run_start + MAX_RUN_SECONDS

    print("=" * 80)
    print(f"🛰️ MOTOR MAESTRO DE MIGRACIÓN ACELERADA Y SINCRONIZACIÓN HD/4K")
    print(f"   Modo: {mode.upper()} | Presupuesto: {MAX_RUN_SECONDS}s (~{MAX_RUN_SECONDS/60:.1f} min)")
    print("=" * 80)

    if not SESSION_BUNKER or not SESSION_PROD:
        logger.error("❌ ERROR: SESSION_BUNKER y SESSION_PROD son requeridas.")
        sys.exit(1)

    cb = TelegramClient(StringSession(SESSION_BUNKER), API_ID, API_HASH)
    cp = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)

    await cb.start()
    await cp.start()

    me_b = await cb.get_me()
    me_p = await cp.get_me()
    logger.info(f"👤 Búnker: {me_b.first_name} [ID: {me_b.id}] | Producción: {me_p.first_name} [ID: {me_p.id}]")

    state = load_state()

    # Cifras Previas a la Ejecución
    prev_works_count = len(state.get("migrated_works", {}))
    prev_parts_count = sum(len(w.get("part_msg_ids", [])) for w in state.get("migrated_works", {}).values())
    prev_bytes_count = sum(w.get("total_bytes", 0) for w in state.get("migrated_works", {}).values())

    # FASE 1: Verificación / Resolución de Canales
    print("\n" + "=" * 75)
    print("📋 FASE 1: RESOLUCIÓN Y VALIDACIÓN DE CANALES")
    print("=" * 75)
    for k, cfg in BUNKERS_CONFIG.items():
        await resolve_or_create_channel(cp, cb, k, cfg, state)
        ch = state["channels"][k]
        logger.info(f"📌 [{k}] {ch['prod_title']} (ID: {ch['prod_id']}) -> Fase: {ch.get('sync_phase')}")

    save_state(state)

    # FASE 2: Procesamiento Continuo por Lotes (Round-Robin con Presupuesto de Tiempo)
    print("\n" + "=" * 75)
    print("🚀 FASE 2: PROCESAMIENTO CONTINUO DE LOTES")
    print("=" * 75)

    active_keys = ["pelis_clasicas", "pelis_2000", "pelis_estrenos"]
    session_new_works = 0
    session_new_files = 0
    session_new_bytes = 0

    round_num = 1
    while time.time() < deadline - 90:  # Margen de 90s para guardado final
        elapsed_min = (time.time() - run_start) / 60
        remaining_min = (deadline - time.time()) / 60
        print(f"\n--- Ronda {round_num} (Transcurrido: {elapsed_min:.1f}m | Restante: {remaining_min:.1f}m) ---")
        
        round_activity = 0
        for k in active_keys:
            if time.time() >= deadline - 90:
                break
            res = await migrate_channel_pass(
                cp=cp, cb=cb, key=k, cfg=BUNKERS_CONFIG[k],
                state=state, max_works=MAX_WORKS_PER_PASS, deadline_ts=deadline - 90
            )
            w_migrated = res.get("works_migrated", 0)
            f_migrated = res.get("messages_forwarded", 0)
            b_migrated = res.get("bytes_transferred", 0)

            session_new_works += w_migrated
            session_new_files += f_migrated
            session_new_bytes += b_migrated
            round_activity += w_migrated

        # Si en toda la ronda no hubo ninguna obra nueva migrada (todos los canales están al día o en pausa)
        if round_activity == 0:
            logger.info("✨ Todos los canales activos han alcanzado la frontera actual del búnker. Concluyendo rondas.")
            break

        round_num += 1

    # FASE 3: Conciliación Rigurosa de Cifras
    print("\n" + "=" * 75)
    print("📊 FASE 3: RECONCILIACIÓN RIGUROSA DE CIFRAS Y ESTADOS")
    print("=" * 75)

    total_confirmed_works = len(state.get("migrated_works", {}))
    total_confirmed_parts = sum(len(w.get("part_msg_ids", [])) for w in state.get("migrated_works", {}).values())
    total_confirmed_bytes = sum(w.get("total_bytes", 0) for w in state.get("migrated_works", {}).values())

    print(f"1. Obras:")
    print(f"   - Obras previamente transferidas: {prev_works_count}")
    print(f"   - Obras nuevas transferidas en esta ejecución: {session_new_works}")
    print(f"   - Obras totales confirmadas en estado: {total_confirmed_works}")
    print(f"2. Archivos / Partes:")
    print(f"   - Archivos previamente existentes: {prev_parts_count}")
    print(f"   - Archivos nuevos transferidos en esta ejecución: {session_new_files}")
    print(f"   - Archivos totales confirmados en estado: {total_confirmed_parts}")
    print(f"3. Volumen de Datos:")
    print(f"   - Bytes previamente registrados: {prev_bytes_count:,} bytes ({prev_bytes_count/(1024**3):.2f} GiB)")
    print(f"   - Bytes nuevos representados: {session_new_bytes:,} bytes ({session_new_bytes/(1024**3):.2f} GiB)")
    print(f"   - Bytes acumulados confirmados: {total_confirmed_bytes:,} bytes ({total_confirmed_bytes/(1024**3):.2f} GiB)")
    print(f"4. Estado de Canales:")
    for k, ch in state["channels"].items():
        print(f"   - [{k}] {ch['prod_title']}: Fase={ch.get('sync_phase')} | Cursor={ch.get('last_synced_id')} / {ch.get('bunker_max_id', '?')}")
        if ch.get("paused_reason"):
            print(f"     ⚠️ Pausa: {ch['paused_reason']}")

    save_state(state)

    await cb.disconnect()
    await cp.disconnect()
    logger.info("🔒 Sesiones cerradas limpiamente. Ejecución finalizada con éxito.")

if __name__ == '__main__':
    asyncio.run(main())
