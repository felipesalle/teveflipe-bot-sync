import os
import sys
import json
import asyncio
import logging
import time
from telethon import TelegramClient
from telethon.sessions import StringSession

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s")
logger = logging.getLogger("AuditCabecerasCenso")

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_BUNKER = os.getenv("SESSION_BUNKER") or ""
SESSION_PROD = os.getenv("SESSION_PROD") or ""

RAR5_SIG = b'Rar!\x1a\x07\x01\x00'
RAR4_SIG = b'Rar!\x1a\x07\x00'
SEVEN_ZIP_SIG = b'7z\xbc\xaf\x27\x1c'
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

    offset = 8 # Tras 'Rar!\x1A\x07\x01\x00'
    
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
            
            # flags check
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

async def run_audit():
    session_str = SESSION_BUNKER or SESSION_PROD
    if not session_str:
        logger.error("No hay sesiones configuradas.")
        return

    if not os.path.exists("rar_candidates.json"):
        logger.error("No se encontró 'rar_candidates.json'.")
        return

    with open("rar_candidates.json", "r", encoding="utf-8") as f:
        candidates = json.load(f)

    total_candidates = len(candidates)
    logger.info(f"Candidatos RAR cargados: {total_candidates}")

    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        logger.error("Cliente no autorizado.")
        await client.disconnect()
        return

    # Buscar canal
    target_channel = None
    async for d in client.iter_dialogs(limit=400):
        s_id = str(d.id)
        d_name = d.name or ""
        if '5498750167' in s_id or '5498750167' in str(abs(d.id)) or 'estrenos hd/4k' in d_name.lower():
            target_channel = d.entity
            logger.info(f"Canal localizado: '{d_name}' (ID: {d.id})")
            break

    if not target_channel:
        logger.error("Canal no encontrado.")
        await client.disconnect()
        return

    sem = asyncio.Semaphore(12)
    processed = 0
    results = {
        "rar5_store_valid": [],
        "rar5_compressed_invalid": [],
        "rar4_invalid": [],
        "raw_split_valid": [],
        "other_invalid": []
    }

    async def audit_item(item):
        nonlocal processed
        msg_id = item["part1_msg_id"]
        async with sem:
            try:
                msg = await client.get_messages(target_channel, ids=msg_id)
                if not msg or not msg.media:
                    results["other_invalid"].append({**item, "reason": "Mensaje o multimedia no disponible"})
                    return

                head = await download_head(client, msg)
                if not head:
                    results["other_invalid"].append({**item, "reason": "Cabecera vacía o fallo descarga"})
                    return

                if head.startswith(RAR5_SIG):
                    desc, is_store, iname = inspect_rar5_header(head)
                    if is_store:
                        results["rar5_store_valid"].append({**item, "inner_name": iname, "format": "RAR 5.0 Store"})
                    else:
                        results["rar5_compressed_invalid"].append({**item, "reason": f"RAR 5.0 Comprimido ({desc})", "inner_name": iname})
                elif head.startswith(RAR4_SIG):
                    results["rar4_invalid"].append({**item, "reason": "RAR 4.x Legacy (No soportado por ExoPlayer)"})
                elif head.startswith(MKV_SIG) or MP4_SIG in head[:32]:
                    results["raw_split_valid"].append({**item, "format": "Raw Split directo"})
                elif head.startswith(ZIP_SIG):
                    results["other_invalid"].append({**item, "reason": "ZIP disfrazado"})
                else:
                    results["other_invalid"].append({**item, "reason": f"Cabecera desconocida: {head[:16].hex()}"})

            except Exception as e:
                results["other_invalid"].append({**item, "reason": f"Excepción: {str(e)}"})
            finally:
                processed += 1
                if processed % 200 == 0 or processed == total_candidates:
                    logger.info(f"  Progreso cabeceras: {processed}/{total_candidates} ({processed*100//total_candidates}%) | Válidas: {len(results['rar5_store_valid'])+len(results['raw_split_valid'])} | Inválidas: {len(results['rar5_compressed_invalid'])+len(results['rar4_invalid'])+len(results['other_invalid'])}")

    logger.info("Iniciando inspección concurrente de cabeceras...")
    start_time = time.time()
    
    # Procesar en bloques para control de memoria y flujo
    chunk_size = 500
    for i in range(0, total_candidates, chunk_size):
        batch = candidates[i:i+chunk_size]
        await asyncio.gather(*(audit_item(it) for it in batch))
        await asyncio.sleep(1) # Pequeño respiro entre lotes

    duration = round(time.time() - start_time, 1)
    logger.info(f"Auditoría de cabeceras finalizada en {duration}s.")

    # Guardar reporte
    with open("resultado_auditoria_cabeceras.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    total_valid = len(results["rar5_store_valid"]) + len(results["raw_split_valid"])
    total_invalid = len(results["rar5_compressed_invalid"]) + len(results["rar4_invalid"]) + len(results["other_invalid"])

    print("\n" + "="*80)
    print("🔬 RESULTADO DE LA AUDITORÍA DE CABECERAS RAR:")
    print("="*80)
    print(f"✅ RAR 5.0 Store (Válidas y Reproducibles):      {len(results['rar5_store_valid']):,}")
    print(f"✅ Raw Split detectado como RAR:                 {len(results['raw_split_valid']):,}")
    print(f"❌ RAR 5.0 Comprimido (Incompatibles - Normal):  {len(results['rar5_compressed_invalid']):,}")
    print(f"❌ RAR 4.x Legacy (Incompatibles):               {len(results['rar4_invalid']):,}")
    print(f"❌ Otros formatos / Errores:                     {len(results['other_invalid']):,}")
    print("-"*80)
    print(f"🟢 TOTAL CANDIDATOS VÁLIDOS:                     {total_valid:,}")
    print(f"🔴 TOTAL CANDIDATOS A ELIMINAR:                  {total_invalid:,}")
    print("="*80)

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(run_audit())
