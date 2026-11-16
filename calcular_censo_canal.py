import os
import sys
import json
import asyncio
import logging
import re
from telethon import TelegramClient
from telethon.sessions import StringSession

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s")
logger = logging.getLogger("CensoCanal")

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_BUNKER = os.getenv("SESSION_BUNKER") or ""
SESSION_PROD = os.getenv("SESSION_PROD") or ""

RAR_PART_REGEX = re.compile(r'(?i)(.*?)[._\s\-\(\[]part(?:e|\s)?0*(\d+)[._\s\-\)\]]*(?:\.rar)?$')
NUM_SPLIT_REGEX = re.compile(r'(?i)(.*?)\.0*(\d{1,4})$')
ZIP_PART_REGEX = re.compile(r'(?i)\.zip(?:\.0*\d+)?$')

async def run_census():
    session_str = SESSION_BUNKER or SESSION_PROD
    if not session_str:
        logger.error("No hay sesiones configuradas.")
        return

    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        logger.error("Cliente Telethon no autorizado.")
        await client.disconnect()
        return

    me = await client.get_me()
    logger.info(f"Conectado como: {me.first_name} (ID: {me.id})")

    # Localizar el canal
    target_channel = None
    async for d in client.iter_dialogs(limit=400):
        s_id = str(d.id)
        d_name = d.name or ""
        if '5498750167' in s_id or '5498750167' in str(abs(d.id)) or 'estrenos hd/4k' in d_name.lower():
            target_channel = d.entity
            logger.info(f"Canal localizado: '{d_name}' (ID: {d.id})")
            break

    if not target_channel:
        logger.error("No se pudo localizar el canal.")
        await client.disconnect()
        return

    c_title = getattr(target_channel, 'title', str(target_channel.id))
    logger.info(f"Iniciando censo completo de TODOS los mensajes de '{c_title}'...")

    total_msgs_scanned = 0
    total_files_scanned = 0
    total_text_cards = 0

    # Estructuras de agrupación
    multipart_groups = {} # base_key -> {title, parts: {num: {id, fn, size_mb}}, is_zip: bool, is_rar: bool, is_split: bool}
    single_files = []     # Archivos directos (.mkv, .mp4 sin partes)
    banned_files = []     # Archivos basura (.txt, .nfo, .exe)
    
    current_card_title = "Sin Título"

    # Recorremos el canal de principio a fin sin límite
    async for m in client.iter_messages(target_channel, limit=None):
        total_msgs_scanned += 1
        if total_msgs_scanned % 2500 == 0:
            logger.info(f"  ⏳ Escaneados {total_msgs_scanned} mensajes... ({len(multipart_groups)} películas multiparte detectadas)")

        if m.action:
            continue

        fn = getattr(getattr(m, 'file', None), 'name', '') or ""
        txt = (m.text or "").strip()
        size_mb = round((m.file.size / (1024*1024)), 1) if m.file else 0

        # Tarjeta informativa de película
        if txt and ("calidad:" in txt.lower() or "partes:" in txt.lower() or "tamaño total:" in txt.lower() or "🎬" in txt):
            total_text_cards += 1
            first_line = txt.split('\n')[0].replace('🎬', '').strip()
            if first_line:
                current_card_title = first_line

        if not fn:
            continue

        total_files_scanned += 1
        fn_lower = fn.lower()

        # 1. Archivos basura conocidos
        if fn_lower.endswith(('.txt', '.nfo', '.torrent', '.iso', '.exe')):
            banned_files.append({"id": m.id, "fn": fn, "size_mb": size_mb})
            continue

        # 2. Detección de partes
        m_rar = RAR_PART_REGEX.search(fn)
        m_num = NUM_SPLIT_REGEX.search(fn)

        if m_rar:
            base_name = m_rar.group(1).strip(' .-_')
            part_num = int(m_rar.group(2))
            
            if base_name not in multipart_groups:
                multipart_groups[base_name] = {
                    "base_key": base_name,
                    "title": current_card_title if current_card_title != "Sin Título" else base_name,
                    "type": "RAR",
                    "parts": {},
                    "msg_ids": []
                }
            multipart_groups[base_name]["parts"][part_num] = {"msg_id": m.id, "fn": fn, "size_mb": size_mb}
            multipart_groups[base_name]["msg_ids"].append(m.id)

        elif m_num:
            base_name = m_num.group(1).strip(' .-_')
            part_num = int(m_num.group(2))
            is_zip_part = bool(ZIP_PART_REGEX.search(base_name))

            if base_name not in multipart_groups:
                multipart_groups[base_name] = {
                    "base_key": base_name,
                    "title": current_card_title if current_card_title != "Sin Título" else base_name,
                    "type": "ZIP_PART" if is_zip_part else "RAW_SPLIT",
                    "parts": {},
                    "msg_ids": []
                }
            multipart_groups[base_name]["parts"][part_num] = {"msg_id": m.id, "fn": fn, "size_mb": size_mb}
            multipart_groups[base_name]["msg_ids"].append(m.id)

        elif ZIP_PART_REGEX.search(fn_lower):
            # Archivo zip suelto
            if fn not in multipart_groups:
                multipart_groups[fn] = {
                    "base_key": fn,
                    "title": current_card_title if current_card_title != "Sin Título" else fn,
                    "type": "ZIP_SINGLE",
                    "parts": {1: {"msg_id": m.id, "fn": fn, "size_mb": size_mb}},
                    "msg_ids": [m.id]
                }

        else:
            # Archivo de video suelto directo (no en partes)
            single_files.append({"id": m.id, "fn": fn, "size_mb": size_mb, "title": current_card_title})

    logger.info("Escaneo completado. Clasificando y generando métricas...")

    # Clasificar el censo de películas
    censo_stats = {
        "canal_nombre": c_title,
        "total_mensajes": total_msgs_scanned,
        "total_archivos": total_files_scanned,
        "fichas_texto": total_text_cards,
        "total_peliculas_por_partes": len(multipart_groups),
        "total_peliculas_archivo_unico": len(single_files),
        "archivos_basura_sueltos": len(banned_files),
        "desglose_partes": {
            "conjuntos_rar": 0,
            "conjuntos_raw_split": 0,
            "conjuntos_zip_incompatibles": 0,
            "conjuntos_incompletos_faltan_partes": 0
        }
    }

    rar_candidates_for_header_audit = []
    incompletas_list = []
    zip_incompatibles_list = []

    for base_key, g in multipart_groups.items():
        parts = g["parts"]
        p_nums = sorted(parts.keys())
        max_p = max(p_nums) if p_nums else 0
        missing = [i for i in range(1, max_p + 1) if i not in parts]

        g_type = g["type"]
        if g_type == "ZIP_PART" or g_type == "ZIP_SINGLE":
            censo_stats["desglose_partes"]["conjuntos_zip_incompatibles"] += 1
            zip_incompatibles_list.append({
                "base_key": base_key,
                "title": g["title"],
                "part_count": len(parts),
                "msg_ids": g["msg_ids"],
                "filenames": [p["fn"] for p in parts.values()]
            })
        elif missing or 1 not in parts:
            censo_stats["desglose_partes"]["conjuntos_incompletos_faltan_partes"] += 1
            incompletas_list.append({
                "base_key": base_key,
                "title": g["title"],
                "missing": missing or ["falta parte 1"],
                "present": p_nums,
                "msg_ids": g["msg_ids"],
                "filenames": [p["fn"] for p in parts.values()]
            })
        elif g_type == "RAW_SPLIT":
            censo_stats["desglose_partes"]["conjuntos_raw_split"] += 1
        elif g_type == "RAR":
            censo_stats["desglose_partes"]["conjuntos_rar"] += 1
            rar_candidates_for_header_audit.append({
                "base_key": base_key,
                "title": g["title"],
                "part1_msg_id": parts[1]["msg_id"],
                "part_count": len(parts),
                "msg_ids": g["msg_ids"],
                "total_mb": sum(p["size_mb"] for p in parts.values()),
                "filenames": [p["fn"] for p in parts.values()]
            })

    output_data = {
        "stats": censo_stats,
        "rar_candidates": rar_candidates_for_header_audit,
        "zip_incompatibles": zip_incompatibles_list,
        "incompletas": incompletas_list,
        "single_files_sample": single_files[:20]
    }

    with open("censo_total_canal.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print("\n" + "="*80)
    print(f"📊 CENSO TOTAL EXACTO DEL CANAL: {c_title}")
    print("="*80)
    print(f"📁 Total Mensajes Escaneados:   {total_msgs_scanned:,}")
    print(f"📎 Total Archivos Físicos:       {total_files_scanned:,}")
    print(f"🎬 PELÍCULAS EN PARTES TOTALES:  {len(multipart_groups):,}")
    print(f"🎞️  Películas de Archivo Único:   {len(single_files):,}")
    print(f"🗑️  Archivos Basura (.txt/.nfo):  {len(banned_files):,}")
    print("-"*80)
    print("🔬 DESGLOSE DE LAS PELÍCULAS EN PARTES:")
    print(f"  • Conjuntos RAR (Candidatos a auditar cabecera): {censo_stats['desglose_partes']['conjuntos_rar']:,}")
    print(f"  • Conjuntos Raw Split (.001/.mkv.001 - Válidos): {censo_stats['desglose_partes']['conjuntos_raw_split']:,}")
    print(f"  • Conjuntos ZIP (.zip.001/.zip - Incompatibles): {censo_stats['desglose_partes']['conjuntos_zip_incompatibles']:,}")
    print(f"  • Conjuntos Rotos (Faltan partes intermedias):  {censo_stats['desglose_partes']['conjuntos_incompletos_faltan_partes']:,}")
    print("="*80)

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(run_census())
