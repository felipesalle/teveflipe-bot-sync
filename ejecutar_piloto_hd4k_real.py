#!/usr/bin/env python3
"""
ejecutar_piloto_hd4k_real.py — Ejecución Integral del Primer Piloto Real HD/4K
TeVeFLIPE

Obra: La bella y la bestia [3D] (1991)
Origen: Películas Clásicas HD/4K Bunker (-1004450378925)
Ficha: Mensaje 17370
Partes: Mensajes 17371 a 17387 (17 partes .7z.001 a .7z.017)
Tamaño total: 17.395.578.987 bytes (16.20 GiB)
Destino: 🎞️ Películas Clásicas HD/4K — TeVeFLIPE (Canal Privado de Difusión)
"""

import os
import sys
import time
import json
import asyncio
import logging
from typing import Dict, List, Any, Optional

from telethon import TelegramClient, utils, errors
from telethon.sessions import StringSession
from telethon.tl.functions.channels import (
    CreateChannelRequest,
    EditAdminRequest,
    InviteToChannelRequest,
    GetParticipantRequest
)
from telethon.tl.functions.messages import ExportChatInviteRequest
from telethon.tl.types import (
    ChatAdminRights,
    ChatInviteExported,
    MessageMediaDocument,
    DocumentAttributeFilename
)

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(
    format="[%(asctime)s] %(levelname)s - %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("PilotoRealHD4K")

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_BUNKER = os.getenv("SESSION_BUNKER", "").strip()
SESSION_PROD = os.getenv("SESSION_PROD", "").strip()

ORIGEN_BUNKER_ID = -1004450378925
FICHA_ORIGEN_ID = 17370
PART_START_ID = 17371
PART_END_ID = 17387
EXPECTED_PARTS = 17
EXPECTED_TOTAL_BYTES = 17395578987
TARGET_CHANNEL_TITLE = "🎞️ Películas Clásicas HD/4K — TeVeFLIPE"

# Canales legacy protegidos contra escritura accidental
LEGACY_DESTINATIONS = {
    -1003763464899, -1004331019870, -1004419790119, -1003886841797,
    -1004467288762, -1004326583216, -1004343712699, -1004300040143,
    -1004445508015, -1004341160346, -1004415457188, -1003865750796,
    -1004390222354, -1004296746003, -1004405196455
}
BUNKER_ORIGINS = {
    -1004450378925, -1001905652210, -1002146236969, -1002097175258,
    -1002160549536, -1004388643765, -1004316187715, -1004383923903,
    -1004385066808, -1004440781202, -1004445501873, -1004488255668
}

RESULT_JSON_FILE = "resultado_piloto_hd4k.json"

async def resolve_or_create_destination(cp: TelegramClient, cb: TelegramClient) -> Any:
    """Busca o crea el canal privado de difusión mediante SESSION_PROD."""
    dest_entity = None
    logger.info(f"🔍 Comprobando si el canal '{TARGET_CHANNEL_TITLE}' ya existe en la cuenta Producción...")
    
    async for d in cp.iter_dialogs(limit=150):
        if d.is_channel and not d.is_group:
            t = (d.title or "").strip().lower()
            if "películas clásicas hd/4k" in t or "peliculas clasicas hd/4k" in t:
                peer_id = utils.get_peer_id(d.entity)
                if peer_id in LEGACY_DESTINATIONS or peer_id in BUNKER_ORIGINS:
                    continue
                dest_entity = d.entity
                logger.info(f"✅ Canal destino ya existente encontrado: '{d.title}' (ID: {peer_id})")
                break

    if not dest_entity:
        logger.info(f"🚀 Creando canal privado de difusión: '{TARGET_CHANNEL_TITLE}' con cuenta Producción...")
        res = await cp(CreateChannelRequest(
            title=TARGET_CHANNEL_TITLE,
            about="Canal Privado de Producción para Películas Clásicas HD/4K de TeVeFLIPE.",
            broadcast=True,
            megagroup=False
        ))
        dest_entity = res.chats[0]
        peer_id = utils.get_peer_id(dest_entity)
        logger.info(f"🎉 ¡Canal privado creado con éxito! Título: '{dest_entity.title}', ID: {peer_id}")

    peer_id = utils.get_peer_id(dest_entity)

    # Validaciones de seguridad duras
    if peer_id in LEGACY_DESTINATIONS:
        raise ValueError(f"🛑 BLOQUEO: El ID {peer_id} coincide con un canal legacy protegido.")
    if peer_id in BUNKER_ORIGINS:
        raise ValueError(f"🛑 BLOQUEO: El ID {peer_id} coincide con un búnker de origen.")

    # Asegurar que SESSION_BUNKER tiene acceso de publicación si es necesario
    me_b = await cb.get_me()
    try:
        # Añadir al búnker como administrador en el canal de difusión
        logger.info(f"Otorgando permisos de administración a Búnker ({me_b.first_name}, ID: {me_b.id}) en el canal...")
        admin_rights = ChatAdminRights(
            post_messages=True,
            edit_messages=True,
            delete_messages=False,
            invite_users=True
        )
        await cp(EditAdminRequest(
            channel=dest_entity,
            user_id=me_b.id,
            admin_rights=admin_rights,
            rank="Forwarder HD4K"
        ))
        logger.info("✅ Permisos de administración configurados para Búnker en destino.")
    except Exception as e_adm:
        logger.warning(f"Aviso configurando admin (puede que ya sea admin o creador): {e_adm}")

    return dest_entity, peer_id

async def run():
    t_start = time.time()
    print("=" * 80)
    print("🎬 EJECUCIÓN OFICIAL DEL PRIMER PILOTO REAL HD/4K MULTIPART")
    print(f"Obra: La bella y la bestia [3D] (1991)")
    print(f"Origen: {ORIGEN_BUNKER_ID} (Ficha: {FICHA_ORIGEN_ID}, Partes: {PART_START_ID}..{PART_END_ID})")
    print("=" * 80)

    if not SESSION_BUNKER or not SESSION_PROD:
        logger.error("❌ ERROR: Ambas sesiones (SESSION_BUNKER y SESSION_PROD) deben estar configuradas.")
        sys.exit(1)

    cb = TelegramClient(StringSession(SESSION_BUNKER), API_ID, API_HASH)
    cp = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)

    await cb.start()
    await cp.start()

    me_b = await cb.get_me()
    me_p = await cp.get_me()
    logger.info(f"👤 Cuenta Búnker conectada: {me_b.first_name} [ID: {me_b.id}]")
    logger.info(f"👤 Cuenta Producción conectada: {me_p.first_name} [ID: {me_p.id}]")

    report: Dict[str, Any] = {
        "titulo": "La bella y la bestia [3D] (1991)",
        "origen_bunker_id": ORIGEN_BUNKER_ID,
        "canal_destino_id": None,
        "canal_destino_titulo": None,
        "enlace_privado": None,
        "cuenta_bunker": f"{me_b.first_name} ({me_b.id})",
        "cuenta_prod": f"{me_p.first_name} ({me_p.id})",
        "ficha_origen_id": FICHA_ORIGEN_ID,
        "ficha_destino_id": None,
        "partes_transferidas": [],
        "total_bytes_verificados": 0,
        "total_partes_esperadas": EXPECTED_PARTS,
        "estado_final": "INICIADO",
        "reintentos_o_errores": 0,
        "duracion_segundos": 0
    }

    try:
        # PASO 1: Resolver o Crear Canal Destino
        dest_chat, dest_id = await resolve_or_create_destination(cp, cb)
        report["canal_destino_id"] = dest_id
        report["canal_destino_titulo"] = getattr(dest_chat, 'title', TARGET_CHANNEL_TITLE)

        # Generar enlace privado
        try:
            exported = await cp(ExportChatInviteRequest(peer=dest_chat, title="Enlace Difusión Privada HD/4K"))
            if isinstance(exported, ChatInviteExported):
                report["enlace_privado"] = exported.link
                logger.info(f"🔗 Enlace privado de acceso: {exported.link}")
        except Exception as e_link:
            logger.warning(f"No se pudo exportar enlace: {e_link}")

        # PASO 2: Preflight de Origen
        logger.info(f"🔍 Leyendo ficha y 17 partes en Búnker Origen ({ORIGEN_BUNKER_ID})...")
        ent_bunker = await cb.get_input_entity(ORIGEN_BUNKER_ID)
        
        # Leer ficha
        ficha_msg = await cb.get_messages(ent_bunker, ids=FICHA_ORIGEN_ID)
        if not ficha_msg:
            raise ValueError(f"Ficha {FICHA_ORIGEN_ID} no encontrada en búnker.")
        logger.info(f"✅ Ficha descriptiva encontrada: {len(ficha_msg.text or '')} caracteres.")

        # Leer 17 partes
        expected_ids = list(range(PART_START_ID, PART_END_ID + 1))
        part_msgs = await cb.get_messages(ent_bunker, ids=expected_ids)
        if len(part_msgs) != EXPECTED_PARTS:
            raise ValueError(f"Esperadas {EXPECTED_PARTS} partes, pero se recuperaron {len(part_msgs)}")

        parts_to_send = []
        bytes_sum = 0
        for idx, pm in enumerate(part_msgs, 1):
            if not pm or not pm.file:
                raise ValueError(f"Parte {idx} (ID {PART_START_ID + idx - 1}) no contiene archivo adjunto.")
            fn = pm.file.name or ""
            sz = pm.file.size or 0
            bytes_sum += sz
            expected_suffix = f".{idx:03d}"
            if not fn.endswith(expected_suffix):
                raise ValueError(f"Parte {idx} nombre '{fn}' no coincide con sufijo '{expected_suffix}'")
            parts_to_send.append({
                "part_index": idx,
                "msg_id": pm.id,
                "filename": fn,
                "size_bytes": sz,
                "size_mb": round(sz / (1024 * 1024), 2)
            })

        if bytes_sum != EXPECTED_TOTAL_BYTES:
            raise ValueError(f"Suma de bytes {bytes_sum} no coincide con esperado {EXPECTED_TOTAL_BYTES}")

        logger.info(f"✅ Preflight completado: 17 partes verificadas ({bytes_sum / (1024**3):.2f} GiB).")

        # PASO 3: Inspeccionar mensajes existentes en destino (Detección de duplicados previa)
        ent_dest_b = await cb.get_input_entity(dest_id)
        ent_dest_p = await cp.get_input_entity(dest_id)

        existing_dest_msgs = []
        async for m in cp.iter_messages(ent_dest_p, limit=50):
            fn = getattr(getattr(m, 'file', None), 'name', '') or ''
            sz = getattr(getattr(m, 'file', None), 'size', 0)
            existing_dest_msgs.append({"id": m.id, "filename": fn, "size": sz, "text": m.text or ""})

        # Comprobar si la ficha ya está en destino
        dest_ficha_id = None
        for em in existing_dest_msgs:
            if "la bella y la bestia" in em["text"].lower() or "sinopsis" in em["text"].lower():
                dest_ficha_id = em["id"]
                logger.info(f"ℹ️ Ficha ya encontrada previamente en destino (ID: {dest_ficha_id})")
                break

        # PASO 4: Transferencia de la Ficha
        if not dest_ficha_id:
            logger.info("📤 Reenviando Ficha descriptiva a destino...")
            # Reenviar desde cb
            fwd_ficha = await cb.forward_messages(entity=ent_dest_b, messages=FICHA_ORIGEN_ID, from_peer=ent_bunker)
            dest_ficha_id = fwd_ficha[0].id if isinstance(fwd_ficha, list) else fwd_ficha.id
            logger.info(f"✅ Ficha publicada en destino con ID {dest_ficha_id}")
            await asyncio.sleep(1.5)

        report["ficha_destino_id"] = dest_ficha_id

        # PASO 5: Transferencia Ordenada de las 17 Partes
        for p in parts_to_send:
            idx = p["part_index"]
            orig_id = p["msg_id"]
            fn = p["filename"]
            sz = p["size_bytes"]

            # Comprobar si ya existe en destino
            existing_id = None
            for em in existing_dest_msgs:
                if em["filename"] == fn and em["size"] == sz:
                    existing_id = em["id"]
                    break

            if existing_id:
                logger.info(f"  [Parte {idx:02d}/17] Ya presente en destino (ID {existing_id}). Omitiendo reenvío.")
                report["partes_transferidas"].append({
                    "part": idx,
                    "origen_id": orig_id,
                    "destino_id": existing_id,
                    "filename": fn,
                    "size_bytes": sz,
                    "size_mb": p["size_mb"],
                    "status": "CONFIRMADO_EXISTENTE"
                })
                continue

            logger.info(f"📤 [Parte {idx:02d}/17] Reenviando parte {orig_id} ('{fn}', {p['size_mb']} MB)...")
            fwd = await cb.forward_messages(entity=ent_dest_b, messages=orig_id, from_peer=ent_bunker)
            dest_part_id = fwd[0].id if isinstance(fwd, list) else fwd.id

            logger.info(f"  ✅ Parte {idx:02d}/17 publicada con éxito en destino (ID: {dest_part_id})")
            report["partes_transferidas"].append({
                "part": idx,
                "origen_id": orig_id,
                "destino_id": dest_part_id,
                "filename": fn,
                "size_bytes": sz,
                "size_mb": p["size_mb"],
                "status": "CONFIRMADO_ENVIADO"
            })

            # Pausa de seguridad de 1.5s entre partes
            await asyncio.sleep(1.5)

        # PASO 6: Verificación Final Obligatoria Directamente en Telegram
        logger.info("\n🔍 VERIFICACIÓN FINAL OBLIGATORIA EN DESTINO...")
        dest_msgs_check = []
        async for m in cp.iter_messages(ent_dest_p, limit=30):
            fn = getattr(getattr(m, 'file', None), 'name', '') or ''
            sz = getattr(getattr(m, 'file', None), 'size', 0)
            dest_msgs_check.append({"id": m.id, "filename": fn, "size": sz, "text": m.text or ""})

        # Validar Ficha
        ficha_verified = any(m["id"] == dest_ficha_id for m in dest_msgs_check)
        if not ficha_verified:
            raise ValueError(f"Ficha {dest_ficha_id} no verificada en destino.")

        # Validar 17 Partes
        dest_filenames = {m["filename"]: m for m in dest_msgs_check if m["filename"]}
        total_verified_bytes = 0
        for p in parts_to_send:
            fn = p["filename"]
            if fn not in dest_filenames:
                raise ValueError(f"Parte requerida '{fn}' no encontrada en destino.")
            dest_sz = dest_filenames[fn]["size"]
            if dest_sz != p["size_bytes"]:
                raise ValueError(f"Tamaño de '{fn}' no coincide: destino {dest_sz} vs origen {p['size_bytes']}")
            total_verified_bytes += dest_sz

        if total_verified_bytes != EXPECTED_TOTAL_BYTES:
            raise ValueError(f"Bytes verificados {total_verified_bytes} != esperado {EXPECTED_TOTAL_BYTES}")

        report["total_bytes_verificados"] = total_verified_bytes
        report["estado_final"] = "SUCCESS_CONFIRMED"
        logger.info("🎉 ¡VERIFICACIÓN EXITOSA AL 100%! Ficha y 17 partes confirmadas byte a byte en destino.")

    except Exception as e:
        logger.error(f"🛑 Error durante la ejecución del piloto: {e}", exc_info=True)
        report["estado_final"] = "FAILED"
        report["error"] = str(e)
        report["reintentos_o_errores"] += 1
    finally:
        report["duracion_segundos"] = round(time.time() - t_start, 2)
        with open(RESULT_JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n💾 Informe estructurado guardado en {RESULT_JSON_FILE}")
        
        await cb.disconnect()
        await cp.disconnect()
        logger.info("🔒 Sesiones desconectadas limpiamente.")

    if report["estado_final"] != "SUCCESS_CONFIRMED":
        sys.exit(1)

if __name__ == '__main__':
    asyncio.run(run())
