import os
import sys
import json
import asyncio
import logging
import re
import time
from telethon import TelegramClient
from telethon.sessions import StringSession

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s")
logger = logging.getLogger("MultiAudit")

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_BUNKER = os.getenv("SESSION_BUNKER") or ""
SESSION_PROD = os.getenv("SESSION_PROD") or ""

CHANNELS = {
    "pelis_2000": {
        "id": -1004420612937,
        "name": "Películas 2000-2019 HD/4K Bunker",
        "type": "movies"
    },
    "pelis_clasicas": {
        "id": -1004450378925,
        "name": "Películas Clásicas HD/4K Bunker",
        "type": "movies"
    },
    "series": {
        "id": -1004457839581,
        "name": "Series HD/4K Bunker",
        "type": "series"
    }
}

RAR_PART_REGEX = re.compile(r'(?i)(.*?)[._\s\-\(\[]part(?:e|\s)?0*(\d+)[._\s\-\)\]]*(?:\.rar)?$')
NUM_SPLIT_REGEX = re.compile(r'(?i)(.*?)\.0*(\d{1,4})$')
ZIP_PART_REGEX = re.compile(r'(?i)\.zip(?:\.0*\d+)?$')

RAR5_SIG = b'Rar!\x1a\x07\x01\x00'
RAR4_SIG = b'Rar!\x1a\x07\x00'
ZIP_SIG = b'PK\x03\x04'
MKV_SIG = b'\x1aE\xdf\xa3'
MP4_SIG = b'ftyp'

def read_vint(buffer, offset):
    res = 0
    shift = 0
    cur = offset
    while cur < len(buffer):
        b = buffer[cur]
        cur += 1
        res |= (b & 0x7F) << shift
        if (b & 0x80) == 0:
            return res, cur - offset
        shift += 7
        if shift >= 64:
            return None
    return None

def inspect_rar5_header(head):
    if len(head) < 16:
        return "Cabecera RAR5 truncada", False, None

    offset = 8
    if offset + 4 > len(head):
        return "Cabecera principal truncada", False, None
    cur = offset + 4
    
    hs = read_vint(head, cur)
    if not hs: return "Error vint hs", False, None
    header_size, hs_len = hs
    cur += hs_len
    
    bt = read_vint(head, cur)
    if not bt: return "Error vint bt", False, None
    b_type, bt_len = bt
    cur += bt_len
    
    if b_type == 4:
        return "Cifrado con contraseña", False, None
    if b_type != 1:
        return f"Bloque no esperado: {b_type}", False, None
        
    bf = read_vint(head, cur)
    if not bf: return "Error vint bf", False, None
    b_flags, bf_len = bf
    cur += bf_len
    
    offset += 4 + hs_len + header_size
    
    while offset + 10 < len(head):
        cur = offset + 4
        hs = read_vint(head, cur)
        if not hs: break
        h_sz, h_len = hs
        cur += h_len
        
        bt = read_vint(head, cur)
        if not bt: break
        b_type, b_len = bt
        cur += b_len
        
        if b_type == 5:
            break
            
        bf = read_vint(head, cur)
        if not bf: break
        b_flags, bf_len = bf
        cur += bf_len
        
        if b_flags & 0x0001:
            ea = read_vint(head, cur)
            if ea: cur += ea[1]
        if b_flags & 0x0002:
            ds = read_vint(head, cur)
            if ds: cur += ds[1]
            
        if b_type == 2:
            ff = read_vint(head, cur)
            if not ff: break
            cur += ff[1]
            
            unp = read_vint(head, cur)
            if not unp: break
            cur += unp[1]
            
            attr = read_vint(head, cur)
            if not attr: break
            cur += attr[1]
            
            f_flags = ff[0]
            if f_flags & 0x0002: cur += 4
            if f_flags & 0x0004: cur += 4
            
            comp = read_vint(head, cur)
            if not comp: break
            comp_info, comp_len = comp
            cur += comp_len
            
            host = read_vint(head, cur)
            if host: cur += host[1]
            
            nl = read_vint(head, cur)
            name = ""
            if nl:
                n_len = nl[0]
                cur += nl[1]
                if cur + n_len <= len(head):
                    try:
                        name = head[cur:cur+n_len].decode('utf-8', errors='ignore')
                    except Exception:
                        pass
                        
            method = (comp_info >> 7) & 0x07
            method_str = {
                0: "Store (Sin compresión)",
                1: "Fastest (Comprimido)",
                2: "Fast (Comprimido)",
                3: "Normal (Comprimido)",
                4: "Good (Comprimido)",
                5: "Best (Comprimido)"
            }.get(method, f"Desconocido ({method})")
            
            is_valid_store = (method == 0)
            return method_str, is_valid_store, name
            
        offset += 4 + h_sz + h_len

    return "No se encontró bloque de archivo", False, None

async def download_head(client, msg):
    chunk = b""
    try:
        async for c in client.iter_download(msg.media, offset=0, request_size=65536):
            chunk += c
            if len(chunk) >= 512:
                break
    except Exception as e:
        logger.debug(f"Error descargando cabecera de msg {msg.id}: {e}")
    return chunk

async def audit_single_channel(client, ch_key, ch_info):
    ch_id = ch_info["id"]
    ch_name = ch_info["name"]
    is_series = (ch_info["type"] == "series")

    logger.info(f"\n{'='*70}\nIniciando auditoría de: {ch_name} (ID: {ch_id})\n{'='*70}")
    
    try:
        entity = await client.get_entity(ch_id)
    except Exception as e:
        logger.error(f"No se pudo resolver entity para {ch_id}: {e}")
        return None

    total_msgs = 0
    total_files = 0
    multipart_groups = {} # group_key -> {base_key, topic_id, title, type, parts: {num: {id, fn, size_mb}}, msg_ids}
    single_files = []
    current_title = "Sin Título"

    logger.info(f"Escaneando historial completo...")
    async for m in client.iter_messages(entity, limit=None):
        total_msgs += 1
        if total_msgs % 3000 == 0:
            logger.info(f"  [{ch_name}] Escaneados {total_msgs} mensajes... ({len(multipart_groups)} conjuntos detectados)")

        if m.action:
            continue

        fn = getattr(getattr(m, 'file', None), 'name', '') or ""
        txt = (m.text or "").strip()
        size_mb = round((m.file.size / (1024*1024)), 1) if m.file else 0
        topic_id = getattr(getattr(m, 'reply_to', None), 'reply_to_top_id', None) or getattr(getattr(m, 'reply_to', None), 'reply_to_msg_id', 0) or 0

        if txt and ("calidad:" in txt.lower() or "partes:" in txt.lower() or "tamaño total:" in txt.lower() or "🎬" in txt or "temporada" in txt.lower()):
            first_line = txt.split('\n')[0].replace('🎬', '').strip()
            if first_line:
                current_title = first_line

        if not fn:
            continue

        total_files += 1
        fn_lower = fn.lower()

        # Ignorar basura evidente
        if fn_lower.endswith(('.txt', '.nfo', '.torrent', '.iso', '.exe')):
            continue

        m_rar = RAR_PART_REGEX.search(fn)
        m_num = NUM_SPLIT_REGEX.search(fn)

        group_id_prefix = f"T{topic_id}_" if is_series else ""

        if m_rar:
            base_name = m_rar.group(1).strip(' .-_')
            part_num = int(m_rar.group(2))
            g_key = f"{group_id_prefix}{base_name}"
            
            if g_key not in multipart_groups:
                multipart_groups[g_key] = {
                    "base_key": base_name,
                    "topic_id": topic_id,
                    "title": current_title if current_title != "Sin Título" else base_name,
                    "type": "RAR",
                    "parts": {},
                    "msg_ids": []
                }
            multipart_groups[g_key]["parts"][part_num] = {"msg_id": m.id, "fn": fn, "size_mb": size_mb}
            multipart_groups[g_key]["msg_ids"].append(m.id)

        elif m_num:
            base_name = m_num.group(1).strip(' .-_')
            part_num = int(m_num.group(2))
            is_zip_part = bool(ZIP_PART_REGEX.search(base_name))
            g_key = f"{group_id_prefix}{base_name}"

            if g_key not in multipart_groups:
                multipart_groups[g_key] = {
                    "base_key": base_name,
                    "topic_id": topic_id,
                    "title": current_title if current_title != "Sin Título" else base_name,
                    "type": "ZIP_PART" if is_zip_part else "RAW_SPLIT",
                    "parts": {},
                    "msg_ids": []
                }
            multipart_groups[g_key]["parts"][part_num] = {"msg_id": m.id, "fn": fn, "size_mb": size_mb}
            multipart_groups[g_key]["msg_ids"].append(m.id)

        elif ZIP_PART_REGEX.search(fn_lower):
            g_key = f"{group_id_prefix}{fn}"
            if g_key not in multipart_groups:
                multipart_groups[g_key] = {
                    "base_key": fn,
                    "topic_id": topic_id,
                    "title": current_title if current_title != "Sin Título" else fn,
                    "type": "ZIP_SINGLE",
                    "parts": {1: {"msg_id": m.id, "fn": fn, "size_mb": size_mb}},
                    "msg_ids": [m.id]
                }
        else:
            single_files.append({"id": m.id, "fn": fn, "size_mb": size_mb, "topic_id": topic_id})

    logger.info(f"[{ch_name}] Censo inicial: {total_msgs} mensajes, {total_files} archivos, {len(multipart_groups)} conjuntos de partes.")

    # Clasificar conjuntos
    raw_splits = []
    zip_incompatibles = []
    incompletas = []
    rar_candidates = []

    for g_key, g in multipart_groups.items():
        parts = g["parts"]
        p_nums = sorted(parts.keys())
        max_p = max(p_nums) if p_nums else 0
        missing = [i for i in range(1, max_p + 1) if i not in parts]

        g_type = g["type"]
        if g_type in ("ZIP_PART", "ZIP_SINGLE"):
            zip_incompatibles.append(g)
        elif missing or 1 not in parts:
            incompletas.append({**g, "missing": missing or ["falta parte 1"], "present": p_nums})
        elif g_type == "RAW_SPLIT":
            raw_splits.append(g)
        elif g_type == "RAR":
            rar_candidates.append(g)

    logger.info(f"[{ch_name}] Pre-clasificación: RawSplit={len(raw_splits)} | ZIP={len(zip_incompatibles)} | Incompletas={len(incompletas)} | RAR={len(rar_candidates)}")

    # Inspección de cabeceras de RAR candidates
    rar_store_valid = []
    rar_compressed_invalid = []
    rar_legacy_invalid = []
    rar_other_invalid = []

    if rar_candidates:
        logger.info(f"[{ch_name}] Inspeccionando cabeceras de {len(rar_candidates)} conjuntos RAR...")
        sem = asyncio.Semaphore(12)
        proc = 0

        async def check_header(g):
            nonlocal proc
            part1_id = g["parts"][1]["msg_id"]
            async with sem:
                try:
                    msg = await client.get_messages(entity, ids=part1_id)
                    if not msg or not msg.media:
                        rar_other_invalid.append({**g, "reason": "No media"})
                        return
                    head = await download_head(client, msg)
                    if not head:
                        rar_other_invalid.append({**g, "reason": "Cabecera vacía"})
                        return

                    if head.startswith(RAR5_SIG):
                        desc, is_store, iname = inspect_rar5_header(head)
                        if is_store:
                            rar_store_valid.append({**g, "inner_name": iname, "format": "RAR 5.0 Store"})
                        else:
                            rar_compressed_invalid.append({**g, "reason": f"RAR 5.0 Comprimido ({desc})", "inner_name": iname})
                    elif head.startswith(RAR4_SIG):
                        rar_legacy_invalid.append({**g, "reason": "RAR 4.x Legacy"})
                    elif head.startswith(MKV_SIG) or MP4_SIG in head[:32]:
                        raw_splits.append(g)
                    elif head.startswith(ZIP_SIG):
                        zip_incompatibles.append(g)
                    else:
                        rar_other_invalid.append({**g, "reason": f"Cabecera desconocida: {head[:16].hex()}"})
                except Exception as e:
                    rar_other_invalid.append({**g, "reason": f"Error: {e}"})
                finally:
                    proc += 1
                    if proc % 300 == 0 or proc == len(rar_candidates):
                        logger.info(f"    [{ch_name}] Cabeceras analizadas: {proc}/{len(rar_candidates)} ({proc*100//len(rar_candidates)}%)")

        chunk_size = 500
        for i in range(0, len(rar_candidates), chunk_size):
            batch = rar_candidates[i:i+chunk_size]
            await asyncio.gather(*(check_header(it) for it in batch))
            await asyncio.sleep(1)

    # Consolidar IDs a eliminar
    ids_to_delete = set()
    for item_list in [zip_incompatibles, incompletas, rar_compressed_invalid, rar_legacy_invalid, rar_other_invalid]:
        for it in item_list:
            for mid in it.get("msg_ids", []):
                ids_to_delete.add(mid)

    total_valid = len(raw_splits) + len(rar_store_valid)
    total_invalid = len(zip_incompatibles) + len(incompletas) + len(rar_compressed_invalid) + len(rar_legacy_invalid) + len(rar_other_invalid)

    report = {
        "channel_key": ch_key,
        "channel_id": ch_id,
        "channel_name": ch_name,
        "channel_type": ch_info["type"],
        "total_mensajes": total_msgs,
        "total_archivos": total_files,
        "total_conjuntos": len(multipart_groups),
        "valid_count": total_valid,
        "invalid_count": total_invalid,
        "desglose": {
            "raw_split_valid": len(raw_splits),
            "rar5_store_valid": len(rar_store_valid),
            "rar5_compressed_invalid": len(rar_compressed_invalid),
            "rar4_legacy_invalid": len(rar_legacy_invalid),
            "zip_incompatibles": len(zip_incompatibles),
            "incompletas": len(incompletas),
            "other_invalid": len(rar_other_invalid)
        },
        "ids_to_delete": sorted(list(ids_to_delete))
    }

    return report

async def main():
    session_str = SESSION_BUNKER or SESSION_PROD
    if not session_str:
        logger.error("No hay sesiones.")
        return

    chosen_target = os.getenv("CHOSEN_TARGET", "all").lower()

    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        logger.error("Cliente Telethon no autorizado.")
        await client.disconnect()
        return

    targets_to_audit = {}
    if chosen_target == "all":
        targets_to_audit = CHANNELS
    elif chosen_target in CHANNELS:
        targets_to_audit = {chosen_target: CHANNELS[chosen_target]}
    else:
        logger.error(f"Target desconocido: {chosen_target}")
        await client.disconnect()
        return

    all_reports = {}
    for k, v in targets_to_audit.items():
        rep = await audit_single_channel(client, k, v)
        if rep:
            all_reports[k] = rep

    with open("reporte_auditoria_multicanal.json", "w", encoding="utf-8") as f:
        json.dump(all_reports, f, ensure_ascii=False, indent=2)

    # Extraer IDs de borrado para cada canal
    del_dict = {k: v["ids_to_delete"] for k, v in all_reports.items()}
    with open("ids_a_borrar_multicanal.json", "w", encoding="utf-8") as f:
        json.dump(del_dict, f, ensure_ascii=False, indent=2)

    print("\n" + "="*80)
    print("RESUMEN GLOBAL DE AUDITORÍA MULTICANAL")
    print("="*80)
    for k, rep in all_reports.items():
        print(f"\n📺 CANAL: {rep['channel_name']}")
        print(f"   • Total Archivos Físicos: {rep['total_archivos']:,}")
        print(f"   • Total Películas / Capítulos en partes: {rep['total_conjuntos']:,}")
        print(f"   • ✅ VÁLIDAS / REPRODUCIBLES (Store/RawSplit): {rep['valid_count']:,}")
        print(f"   • ❌ INCOMPATIBLES A BORRAR: {rep['invalid_count']:,} ({len(rep['ids_to_delete']):,} archivos)")
        print(f"      - RAR 5.0 Comprimidos: {rep['desglose']['rar5_compressed_invalid']}")
        print(f"      - RAR 4.x Legacy:      {rep['desglose']['rar4_legacy_invalid']}")
        print(f"      - Formato ZIP:         {rep['desglose']['zip_incompatibles']}")
        print(f"      - Incompletas/Rotas:   {rep['desglose']['incompletas']}")
    print("="*80)

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
