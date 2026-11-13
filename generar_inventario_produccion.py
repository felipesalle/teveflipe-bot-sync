import os
import sys
import json
import asyncio
import logging
import re
import unicodedata
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetForumTopicsRequest

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("GenerarInventario")

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD") or ""
MAP_FILE = "canales_map.json"
INVENTARIO_FILE = "inventario_produccion.json"

SERIES_EPISODE_REGEX = re.compile(
    r'(?i)(?:\b[sS](\d{1,2})[eE](\d{1,2})\b|\b(\d{1,2})x(\d{1,2})\b|\bcap[ií]tulo\s*(\d+)|\bepisodio\s*(\d+))'
)

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    text = re.sub(r'[^a-zA-Z0-9\s]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip().lower()

def clean_for_search(text: str, filename: str) -> tuple[str, str]:
    raw = (text or "").strip()
    if not raw and filename:
        raw = os.path.splitext(filename)[0]
        
    line = raw.split("\n")[0].strip()
    line = re.sub(r"^[🎬📺🎥🎞️👶💥🥢✨📼🌍🎸🪐\[\(#\s*]+", "", line)
    line = re.sub(r"\[.*?\]|\(.*?\)", "", line)
    line = re.sub(r"(?i)\b(1080p|720p|4k|2160p|bluray|web-dl|webdl|webrip|hdrip|x264|x265|hevc|aac|dts|dual|latino|castellano|subtitulado|sub|temporada|capitulo|completa|t\d+|s\d+|e\d+|cap\b).*$", "", line)
    line = re.sub(r"[._\-–—]", " ", line)
    line = re.sub(r"\s+", " ", line).strip()
    
    match_year = re.search(r"\b(19\d{2}|20\d{2})\b", raw)
    year = match_year.group(1) if match_year else ""
    return line, year

def extract_episode_tag(text: str, filename: str) -> str:
    combined = f"{text or ''} {filename or ''}"
    m = SERIES_EPISODE_REGEX.search(combined)
    if m:
        # SxxExx o xxXxx
        if m.group(1) and m.group(2):
            return f"s{int(m.group(1)):02d}e{int(m.group(2)):02d}"
        if m.group(3) and m.group(4):
            return f"s{int(m.group(3)):02d}e{int(m.group(4)):02d}"
        if m.group(5):
            return f"cap_{int(m.group(5)):03d}"
        if m.group(6):
            return f"cap_{int(m.group(6)):03d}"
    return ""

async def index_diffusion_channel(client, channel_entity, channel_info):
    c_nombre = channel_info["nombre"]
    logger.info(f"Scanning canal difusión: {c_nombre}...")
    
    filenames = set()
    fingerprints = set()
    items = []
    
    count = 0
    async for m in client.iter_messages(channel_entity, limit=None):
        if m.action:
            continue
        fn = getattr(getattr(m, 'file', None), 'name', '') or ""
        txt = m.text or ""
        
        if not fn and not txt:
            continue
            
        count += 1
        fn_clean = fn.lower().strip()
        if fn_clean:
            filenames.add(fn_clean)
            # Para multipartes .7z.001 o .part1.rar, guardar también el prefijo base
            multipart_base = re.sub(r'(?i)\.(?:part\d+\.rar|7z\.\d+|\d{2,4})$', '', fn_clean)
            if multipart_base != fn_clean:
                filenames.add(multipart_base)
                
        title, year = clean_for_search(txt, fn)
        norm_title = normalize_text(title)
        if norm_title:
            fp = f"{norm_title} {year}".strip()
            fingerprints.add(fp)
            fingerprints.add(norm_title)
            items.append({
                "msg_id": m.id,
                "title": title,
                "norm_title": norm_title,
                "year": year,
                "filename": fn
            })
            
    logger.info(f"  -> Total procesados en '{c_nombre}': {count} mensajes ({len(filenames)} archivos únicos, {len(fingerprints)} huellas).")
    return {
        "tipo": "difusion",
        "total_mensajes": count,
        "filenames": list(filenames),
        "fingerprints": list(fingerprints),
        "items": items
    }

async def index_forum_channel(client, channel_entity, channel_info):
    c_nombre = channel_info["nombre"]
    logger.info(f"Scanning supergrupo/foro: {c_nombre}...")
    
    topics_dict = {}
    filenames = set()
    
    # 1. Obtener todos los temas del foro
    offset_date = None
    offset_id = 0
    offset_topic = 0
    all_topics = []
    
    while True:
        try:
            res = await client(GetForumTopicsRequest(
                peer=channel_entity,
                offset_date=offset_date,
                offset_id=offset_id,
                offset_topic=offset_topic,
                limit=100
            ))
            if not res.topics:
                break
            all_topics.extend(res.topics)
            if len(res.topics) < 100:
                break
            offset_topic = res.topics[-1].id
            offset_id = res.topics[-1].top_message
            offset_date = res.topics[-1].date
        except Exception as te:
            logger.warning(f"Aviso obteniendo topics en '{c_nombre}': {te}")
            break
            
    logger.info(f"  -> Encontrados {len(all_topics)} temas en '{c_nombre}'.")
    
    for t in all_topics:
        t_id = t.id
        t_title = t.title or f"Topic {t_id}"
        t_norm = normalize_text(t_title)
        
        episodes_in_topic = set()
        topic_files = []
        
        try:
            async for m in client.iter_messages(channel_entity, reply_to=t_id, limit=None):
                if m.action:
                    continue
                fn = getattr(getattr(m, 'file', None), 'name', '') or ""
                txt = m.text or ""
                if fn:
                    fn_clean = fn.lower().strip()
                    filenames.add(fn_clean)
                    topic_files.append(fn_clean)
                ep_tag = extract_episode_tag(txt, fn)
                if ep_tag:
                    episodes_in_topic.add(ep_tag)
        except Exception as me:
            logger.warning(f"Error leyendo topic '{t_title}' (ID {t_id}): {me}")
            
        topics_dict[t_norm] = {
            "topic_id": t_id,
            "title": t_title,
            "episodes": list(episodes_in_topic),
            "files": topic_files
        }
        
    return {
        "tipo": "foro",
        "total_temas": len(all_topics),
        "filenames": list(filenames),
        "temas": topics_dict
    }

async def main():
    print("=" * 70)
    print("📦 GENERADOR DE INVENTARIO MAESTRO DE PRODUCCIÓN (ANTI-DUPLICADOS)")
    print("=" * 70)
    
    if not SESSION_PROD:
        logger.error("❌ ERROR: SESSION_PROD no configurada.")
        sys.exit(1)
        
    cp = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)
    await cp.start()
    
    me_p = await cp.get_me()
    logger.info(f"Conectado como: {me_p.first_name} (ID: {me_p.id})")
    
    logger.info("Precargando diálogos...")
    await cp.get_dialogs(limit=None)
    
    if not os.path.exists(MAP_FILE):
        logger.error(f"❌ No existe {MAP_FILE}.")
        await cp.disconnect()
        sys.exit(1)
        
    with open(MAP_FILE, "r", encoding="utf-8") as f:
        canales = json.load(f)
        
    inventario_global = {
        "generated_at": str(asyncio.get_event_loop().time()),
        "canales": {}
    }
    
    for c in canales:
        if not c.get("activo", True) or not c.get("produccion_id"):
            continue
            
        c_id = c["id"]
        c_nombre = c["nombre"]
        p_id = c["produccion_id"]
        is_forum = c.get("is_forum", False)
        
        try:
            ent_prod = await cp.get_input_entity(p_id)
            if not is_forum:
                data = await index_diffusion_channel(cp, ent_prod, c)
            else:
                data = await index_forum_channel(cp, ent_prod, c)
                
            inventario_global["canales"][c_id] = data
            logger.info(f"✅ Canal '{c_nombre}' indexado con éxito.")
            await asyncio.sleep(1.0)
        except Exception as e:
            logger.error(f"❌ Error indexando '{c_nombre}': {e}")
            
    with open(INVENTARIO_FILE, "w", encoding="utf-8") as f:
        json.dump(inventario_global, f, ensure_ascii=False, indent=2)
        
    logger.info(f"\n🎉 ¡Inventario completado y guardado en '{INVENTARIO_FILE}'!")
    await cp.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
