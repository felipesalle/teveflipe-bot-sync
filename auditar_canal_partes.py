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
logger = logging.getLogger("AuditCanalPartes")

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
    """Lee un entero de longitud variable (vint) de RAR 5.0"""
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
    """Analiza la cabecera RAR5 para comprobar si es Store o comprimido."""
    if len(head) < 16:
        return "Cabecera RAR5 truncada", False, None

    offset = 8 # Tras 'Rar!\x1A\x07\x01\x00'
    
    # Main Archive Header
    if offset + 4 > len(head):
        return "Cabecera principal RAR5 truncada", False, None
    cur = offset + 4 # Saltar CRC
    
    hs = read_vint(head, cur)
    if not hs: return "Error leyendo header_size", False, None
    header_size, hs_len = hs
    cur += hs_len
    
    bt = read_vint(head, cur)
    if not bt: return "Error leyendo block_type", False, None
    b_type, bt_len = bt
    cur += bt_len
    
    if b_type == 4:
        return "Cifrado con contraseña", False, None
    if b_type != 1:
        return f"Bloque no esperado: {b_type}", False, None
        
    bf = read_vint(head, cur)
    if not bf: return "Error leyendo flags", False, None
    b_flags, bf_len = bf
    cur += bf_len
    
    is_multivolume = bool(b_flags & 0x0001)
    
    # Saltar al siguiente bloque
    offset += 4 + hs_len + header_size
    
    # Buscar bloque de archivo (Type 2)
    while offset + 10 < len(head):
        cur = offset + 4 # saltar CRC
        hs = read_vint(head, cur)
        if not hs: break
        h_sz, h_len = hs
        cur += h_len
        
        bt = read_vint(head, cur)
        if not bt: break
        b_type, b_len = bt
        cur += b_len
        
        if b_type == 5: # End of archive
            break
            
        bf = read_vint(head, cur)
        if not bf: break
        b_flags, bf_len = bf
        cur += bf_len
        
        # Extra area
        if b_flags & 0x0001:
            ea = read_vint(head, cur)
            if ea: cur += ea[1]
        # Data size
        if b_flags & 0x0002:
            ds = read_vint(head, cur)
            if ds: cur += ds[1]
            
        if b_type == 2: # File Header
            ff = read_vint(head, cur)
            if not ff: break
            f_flags, ff_len = ff
            cur += ff_len
            
            unp = read_vint(head, cur)
            if not unp: break
            unpacked_sz, unp_len = unp
            cur += unp_len
            
            attr = read_vint(head, cur)
            if not attr: break
            cur += attr[1]
            
            if f_flags & 0x0002: cur += 4 # mtime
            if f_flags & 0x0004: cur += 4 # crc32
            
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
                        
            # Bits 7..9 del comp_info: 0 = Store, 1 = Fastest, 2 = Fast, 3 = Normal, etc.
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

    return "No se encontró cabecera de archivo válida", False, None

async def inspect_first_bytes(client, entity, msg):
    """Descarga los primeros 64 KB de un mensaje multimedia para analizar sus magic bytes."""
    try:
        data = await client.download_media(msg, file=bytes, thumb=-1)
        # Si download_media descarga todo o no soporta offset directo en bytes,
        # iteramos los primeros chunks del archivo con client.iter_download
        chunk = b""
        async for c in client.iter_download(msg.media, offset=0, limit=65536):
            chunk += c
            if len(chunk) >= 65536:
                break
        return chunk[:65536]
    except Exception as e:
        logger.warning(f"Error descargando fragmento inicial de msg {msg.id}: {e}")
        return b""

async def run_audit():
    session_str = SESSION_BUNKER or SESSION_PROD
    if not session_str:
        logger.error("No hay sesiones configuradas en el entorno.")
        return

    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        logger.error("Cliente Telethon no autorizado.")
        await client.disconnect()
        return

    me = await client.get_me()
    logger.info(f"Conectado como: {me.first_name} (ID: {me.id})")

    # Identificar el canal
    target_channel = None
    target_candidates = [-1005498750167, -5498750167, 5498750167]
    
    # Primero buscar en dialogs
    logger.info("Buscando canal en los diálogos del usuario...")
    async for d in client.iter_dialogs(limit=400):
        s_id = str(d.id)
        d_name = d.name or ""
        if '5498750167' in s_id or '5498750167' in str(abs(d.id)) or 'australia' in d_name.lower():
            target_channel = d.entity
            logger.info(f"¡Canal encontrado en diálogos! Nombre: '{d_name}', ID: {d.id}")
            break

    if not target_channel:
        for cid in target_candidates:
            try:
                target_channel = await client.get_entity(cid)
                logger.info(f"Canal resuelto directamente con get_entity({cid}): {getattr(target_channel, 'title', cid)}")
                break
            except Exception as ec:
                logger.debug(f"Fallo get_entity({cid}): {ec}")

    if not target_channel:
        logger.error("No se pudo localizar el canal https://web.telegram.org/a/#-5498750167. Listando canales del usuario...")
        async for d in client.iter_dialogs(limit=50):
            if d.is_channel or d.is_group:
                print(f"  • {d.name} (ID: {d.id})")
        await client.disconnect()
        return

    c_title = getattr(target_channel, 'title', str(target_channel.id))
    logger.info(f"Iniciando escaneo exhaustivo de: '{c_title}' (ID: {target_channel.id})")

    # Leer todos los mensajes del canal
    all_messages = []
    async for m in client.iter_messages(target_channel, limit=1000):
        if not m.action and (m.file or m.text):
            all_messages.append(m)

    logger.info(f"Se recolectaron {len(all_messages)} mensajes con contenido.")

    # Agrupar por película/conjunto
    # Buscamos textos con "Calidad:", "Partes:", títulos o nombres de archivo
    groups = {}
    current_movie = "Sin Título"
    
    # Procesar en orden cronológico inverso
    for m in all_messages:
        fn = getattr(getattr(m, 'file', None), 'name', '') or ""
        txt = (m.text or "").strip()
        
        # Detectar ficha de película
        if txt and ("calidad:" in txt.lower() or "partes:" in txt.lower() or "tamaño total:" in txt.lower() or "🎬" in txt):
            # Extraer título de la primera línea
            first_line = txt.split('\n')[0].replace('🎬', '').strip()
            current_movie = first_line or "Película Desconocida"

        # Nombre base para agrupación
        base_key = None
        part_idx = 1
        
        if fn:
            # Detectar .partX.rar
            m_rar = re.search(r'(?i)(.*?)[._\s\-\(\[]part(?:e|\s)?0*(\d+)[._\s\-\)\]]*(?:\.rar)?$', fn)
            # Detectar .00X o .mkv.00X
            m_split = re.search(r'(?i)(.*?)\.0*(\d{1,4})$', fn)
            
            if m_rar:
                base_key = m_rar.group(1).strip(' .-_')
                part_idx = int(m_rar.group(2))
            elif m_split:
                base_key = m_split.group(1).strip(' .-_')
                part_idx = int(m_split.group(2))
            else:
                base_key = os.path.splitext(fn)[0]
                part_idx = 1
        elif txt:
            base_key = current_movie
        else:
            base_key = f"msg_{m.id}"

        if base_key not in groups:
            groups[base_key] = {
                "title": current_movie if current_movie != "Sin Título" else base_key,
                "parts": {},
                "info_text": txt if ("calidad:" in txt.lower() or "partes:" in txt.lower()) else "",
                "messages": []
            }
        
        groups[base_key]["messages"].append(m)
        if fn:
            groups[base_key]["parts"][part_idx] = {
                "msg_id": m.id,
                "filename": fn,
                "size_mb": round((m.file.size / (1024*1024)), 1) if m.file else 0,
                "msg": m
            }

    logger.info(f"Se identificaron {len(groups)} películas/conjuntos en el canal.")

    # Analizar cada película
    audit_results = []
    
    for base_key, gdata in groups.items():
        parts = gdata["parts"]
        if not parts:
            continue
            
        p_nums = sorted(parts.keys())
        p_count = len(p_nums)
        expected_max = max(p_nums) if p_nums else 0
        total_size = sum(p["size_mb"] for p in parts.values())
        
        p1 = parts.get(1)
        if not p1:
            audit_results.append({
                "title": gdata["title"],
                "base_key": base_key,
                "parts_count": p_count,
                "total_size_mb": total_size,
                "status": "❌ ERROR: FALTA PARTE 1",
                "details": f"Falta parte 1. Partes presentes: {p_nums}",
                "filenames": [p["filename"] for p in parts.values()]
            })
            continue

        # Verificar si faltan partes intermedias
        missing = [i for i in range(1, expected_max + 1) if i not in parts]
        if missing:
            audit_results.append({
                "title": gdata["title"],
                "base_key": base_key,
                "parts_count": p_count,
                "total_size_mb": total_size,
                "status": "❌ ERROR: PARTES INCOMPLETAS",
                "details": f"Faltan las partes: {missing}",
                "filenames": [p["filename"] for p in parts.values()]
            })
            continue

        # Descargar cabecera de la Parte 1 para análisis binario
        fn1 = p1["filename"]
        logger.info(f"Analizando cabecera de '{gdata['title']}' ({fn1})...")
        head = await inspect_first_bytes(client, target_channel, p1["msg"])
        
        format_type = "Desconocido"
        compression_method = "N/A"
        teveflipe_status = "❓ INDETERMINADO"
        details = ""

        if head.startswith(RAR4_SIG):
            format_type = "RAR 4.x"
            compression_method = "Formato Antiguo"
            teveflipe_status = "❌ INCOMPATIBLE"
            details = "Formato RAR 4.x obsoleto. TeVeFLIPE requiere RAR 5.0 Store o Raw Split."
        elif head.startswith(RAR5_SIG):
            format_type = "RAR 5.0"
            comp_res, is_store, inner_name = inspect_rar5_header(head)
            compression_method = comp_res
            if is_store:
                teveflipe_status = "✅ 100% REPRODUCIBLE"
                details = f"RAR 5.0 Store (sin compresión). Fichero interno: '{inner_name or 'video'}'."
            else:
                teveflipe_status = "❌ ERROR: COMPRIMIDO"
                details = f"RAR 5.0 con {comp_res}. ExoPlayer no puede descomprimir al vuelo."
        elif head.startswith(SEVEN_ZIP_SIG):
            format_type = "7-Zip (7z)"
            teveflipe_status = "⚠️ VERIFICAR"
            details = "Contenedor 7z detectado. Requiere modo Store (Copy) para streaming."
        elif head.startswith(ZIP_SIG):
            format_type = "ZIP Estándar"
            compression_method = "Deflate"
            teveflipe_status = "❌ INCOMPATIBLE"
            details = "Archivo ZIP comprimido. No reproducible en streaming."
        elif head.startswith(MKV_SIG):
            format_type = "Raw Split (Matroska MKV)"
            compression_method = "Sin compresión (Raw bytes)"
            teveflipe_status = "✅ 100% REPRODUCIBLE"
            details = "Fragmento binario puro MKV. Reproducción nativa inmediata."
        elif b'ftyp' in head[:32]:
            format_type = "Raw Split (MP4)"
            compression_method = "Sin compresión (Raw bytes)"
            teveflipe_status = "✅ 100% REPRODUCIBLE"
            details = "Fragmento binario puro MP4. Reproducción nativa inmediata."
        else:
            format_type = "Binario / Otro"
            details = f"Primeros bytes: {head[:16].hex()}"
            teveflipe_status = "⚠️ REVISAR"

        audit_results.append({
            "title": gdata["title"],
            "base_key": base_key,
            "parts_count": p_count,
            "total_size_mb": total_size,
            "format": format_type,
            "compression": compression_method,
            "status": teveflipe_status,
            "details": details,
            "filenames": [p["filename"] for p in parts.values()]
        })

    # Guardar reporte JSON
    report_file = "reporte_auditoria_canal_partes.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(audit_results, f, ensure_ascii=False, indent=2)

    logger.info(f"Auditoría finalizada. Resultados guardados en {report_file}.")
    
    # Imprimir resumen
    print("\n" + "="*80)
    print(f"📊 RESUMEN DE AUDITORÍA: {c_title}")
    print("="*80)
    total_pelis = len(audit_results)
    ok_count = sum(1 for r in audit_results if "✅" in r["status"])
    err_count = sum(1 for r in audit_results if "❌" in r["status"])
    warn_count = sum(1 for r in audit_results if "⚠️" in r["status"])
    
    print(f"Total Películas Auditadas: {total_pelis}")
    print(f"  ✅ 100% Reproducibles en TeVeFLIPE: {ok_count}")
    print(f"  ❌ Con Error o Incompatibles:       {err_count}")
    print(f"  ⚠️  Advertencias / Revisar:           {warn_count}")
    print("-"*80)
    
    for r in audit_results:
        print(f"\n🎬 {r['title']} ({r['parts_count']} partes - {r['total_size_mb']:.1f} MB)")
        print(f"   • Formato: {r.get('format', 'N/A')} | Compresión: {r.get('compression', 'N/A')}")
        print(f"   • Estado TeVeFLIPE: {r['status']}")
        print(f"   • Detalle: {r['details']}")
        print(f"   • Archivos: {', '.join(r['filenames'])}")

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(run_audit())
