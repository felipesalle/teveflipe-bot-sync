import asyncio
import io
import unicodedata
import json
import logging
import os
import random
import re
import sys
import requests
from telethon import TelegramClient, utils, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import (
    ForwardMessagesRequest,
    CreateForumTopicRequest,
    GetForumTopicsRequest,
    ToggleNoForwardsRequest
)

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("SyncNovedadesGlobal")

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD") or ""

COMMUNITY_GROUP_ID = int(os.getenv("COMMUNITY_GROUP_ID", "-1003990716596"))
COMMUNITY_TOPIC_ID = int(os.getenv("COMMUNITY_TOPIC_ID", "22"))
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "2b7cd7b237fe99884613b230a910a09c")

MAP_FILE = "canales_map.json"
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "5"))

def load_json(filepath: str, default=None):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Error leyendo {filepath}: {e}")
    return default() if callable(default) else (default or {})

def save_json(filepath: str, data):
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error guardando {filepath}: {e}")

async def ensure_connected(client: TelegramClient, name: str = "Client"):
    if not client.is_connected():
        logger.info(f"🔄 Cliente {name} desconectado. Reconectando...")
        try:
            await client.connect()
            logger.info(f"✅ Cliente {name} conectado exitosamente.")
        except Exception as e:
            logger.warning(f"⚠️ Error conectando {name}: {e}. Reintentando...")
            await asyncio.sleep(3)
            await client.connect()

def clean_for_search(text: str, filename: str) -> tuple[str, str]:
    raw = (text or "").strip()
    if not raw and filename:
        raw = os.path.splitext(filename)[0]
        
    line = raw.split("\n")[0].strip()
    line = re.sub(r"^[🎬📺🎥🎞️👶💥🥢✨📼🌍🎸🪐\[\(#\s*]+", "", line)
    line = re.sub(r"\[.*?\]|\(.*?\)", "", line)
    line = re.sub(r"(?i)\b(1080p|720p|4k|2160p|bluray|web-dl|webrip|hdrip|x264|x265|hevc|aac|dts|dual|latino|castellano|subtitulado|sub|temporada|capitulo|completa|t\d+|s\d+|e\d+|cap\b).*$", "", line)
    line = re.sub(r"[._\-–—]", " ", line)
    line = re.sub(r"\s+", " ", line).strip()
    
    match_year = re.search(r"\b(19\d{2}|20\d{2})\b", raw)
    year = match_year.group(1) if match_year else ""
    return line, year

def get_tmdb_card(query: str, year: str = "") -> dict:
    default_meta = {
        "title": query,
        "year": year,
        "overview": "",
        "poster_url": None,
        "rating": 0.0
    }
    if not TMDB_API_KEY or not query:
        return default_meta
        
    try:
        url = "https://api.themoviedb.org/3/search/multi"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "es-ES",
            "include_adult": "false"
        }
        if year:
            params["year"] = year
            
        res = requests.get(url, params=params, timeout=5).json()
        results = res.get("results", [])
        if not results:
            if year:
                params.pop("year", None)
                res = requests.get(url, params=params, timeout=5).json()
                results = res.get("results", [])
                
        if results:
            best = results[0]
            title = best.get("title") or best.get("name") or query
            date_str = best.get("release_date") or best.get("first_air_date") or ""
            res_year = date_str[:4] if date_str else year
            poster_path = best.get("poster_path")
            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
            
            return {
                "title": title,
                "year": res_year,
                "overview": best.get("overview", "").strip(),
                "poster_url": poster_url,
                "rating": round(best.get("vote_average", 0.0), 1)
            }
    except Exception as e:
        logger.warning(f"Error consultando TMDB para '{query}': {e}")
        
    return default_meta

NON_DOC_KEYWORDS = [
    "cuarto milenio", "horizonte", "el hormiguero", "la resistencia", "la revuelta",
    "el chiringuito", "masterchef", "supervivientes", "gran hermano", "gh vip",
    "la isla de las tentaciones", "first dates", "salvame", "deluxe", "fiesta",
    "la ruleta de la suerte", "pasapalabra", "tu cara me suena", "got talent",
    "la voz", "operacion triunfo", "ot 20", "pesadilla en la cocina", "equipodeinvestigacion",
    "equipo de investigacion", "la sexta noche", "la sexta columna", "al rojo vivo",
    "espejo publico", "el programa de ana rosa", "vamos a ver", "y ahora sonsoles",
    "cuatro al dia", "telediario", "antena 3 noticias", "informativos telecinco",
    "noticias cuatro", "la noche en 24h", "el intermediario", "el intermedio",
    "el club de la comedia", "ilustres ignorantes", "nadie sabe nada"
]

DOC_KEYWORDS = [
    "documental", "docu", "bbc", "national geographic", "nat geo", "discovery",
    "history channel", "netflix doc", "biografia", "naturaleza", "planeta",
    "universo", "historia de", "la segunda guerra", "la primera guerra",
    "secretos de", "misterios de", "vida salvaje", "fauna", "oceano", "dinosaurios",
    "cosmos", "apolo", "nasa", "expedicion", "arqueologia", "imperio", "civilizacion",
    "egipto", "roma", "grecia", "ciencia", "origen de"
]

def is_valid_documentary(msg) -> bool:
    text = (msg.text or "").lower()
    fname = (msg.file.name.lower() if msg.file and hasattr(msg.file, 'name') and msg.file.name else "")
    combined = f"{text} {fname}"
    
    for kw in NON_DOC_KEYWORDS:
        if kw in combined:
            return False
            
    for kw in DOC_KEYWORDS:
        if kw in combined:
            return True
            
    return False

SERIES_EPISODE_REGEX = re.compile(
    r'(?i)(?:\b[sS]\d{1,2}[eE]\d{1,2}\b|\b\d{1,2}x\d{1,2}\b|\bcap[ií]tulo\s*\d+|\btemporada\s*\d+|\bseason\s*\d+)'
)

def is_series_episode(text: str, filename: str) -> bool:
    content = f"{text or ''} {filename or ''}"
    return bool(SERIES_EPISODE_REGEX.search(content))

async def sync_channel_peliculas(cp, c, ent_bunker, ent_prod, new_msgs):
    # 1. Obtener historial reciente de Producción para armar caché anti-duplicados
    existing_fingerprints = set()
    try:
        await ensure_connected(cp, "Producción")
        async for pm in cp.iter_messages(ent_prod, limit=250):
            pfname = pm.file.name if pm.file and hasattr(pm.file, 'name') and pm.file.name else ""
            ptext = pm.text or ""
            pq, py = clean_for_search(ptext, pfname)
            if pq:
                key = f"{pq.lower()} {py}".strip()
                existing_fingerprints.add(key)
                existing_fingerprints.add(pq.lower().strip())
            if pfname:
                existing_fingerprints.add(pfname.lower().strip())
    except Exception as e:
        logger.warning(f"No se pudo consultar historial reciente de Producción en '{c['nombre']}': {e}")

    # 2. Filtrar mensajes descartando series y duplicados existentes
    processed_items = []
    last_processed_id = c.get("ultimo_id_sincronizado", 0)

    for m in new_msgs:
        fname = m.file.name if m.file and hasattr(m.file, 'name') and m.file.name else ""
        text = m.text or ""

        # Omitir episodios de series infiltrados en canales de películas
        if is_series_episode(text, fname):
            logger.info(f"🚫 Omitiendo episodio de serie en '{c['nombre']}' (Msg {m.id}): {fname or text[:35]}")
            processed_items.append((m.id, None, None, None, "skip"))
            continue

        q, y = clean_for_search(text, fname)
        title_key = f"{q.lower()} {y}".strip() if q else ""

        # Omitir si ya existe en Producción
        if (title_key and title_key in existing_fingerprints) or (q and q.lower().strip() in existing_fingerprints) or (fname and fname.lower().strip() in existing_fingerprints):
            logger.info(f"⏩ Omitiendo '{q} ({y})' [Msg {m.id}] en '{c['nombre']}': ya existe en Producción.")
            processed_items.append((m.id, None, None, None, "skip"))
            continue

        # Mensaje válido para reenvío
        processed_items.append((m.id, m, q, y, "forward"))
        if title_key:
            existing_fingerprints.add(title_key)
        if q:
            existing_fingerprints.add(q.lower().strip())
        if fname:
            existing_fingerprints.add(fname.lower().strip())

    titles_added = []
    max_synced_id = last_processed_id

    # 3. Reenviar en bloques solo los mensajes marcados para "forward"
    to_forward = [item for item in processed_items if item[4] == "forward"]

    if not to_forward:
        # Todos los mensajes nuevos fueron descartados/duplicados; avanzamos hasta el último ID visto
        if processed_items:
            max_synced_id = max(item[0] for item in processed_items)
        return titles_added, max_synced_id

    msg_ids = [item[0] for item in to_forward]
    forward_dict = {item[0]: (item[1], item[2], item[3]) for item in to_forward}

    for i in range(0, len(msg_ids), CHUNK_SIZE):
        chunk = msg_ids[i:i + CHUNK_SIZE]
        chunk_ok = False

        for attempt in range(1, 4):
            try:
                await ensure_connected(cp, "Producción")
                await cp(ForwardMessagesRequest(
                    from_peer=ent_bunker,
                    to_peer=ent_prod,
                    id=chunk,
                    random_id=[random.randint(1, 2**63 - 1) for _ in chunk],
                    drop_author=True
                ))
                chunk_ok = True
                break
            except errors.FloodWaitError as fe:
                logger.warning(f"FloodWait de {fe.seconds}s. Esperando...")
                await asyncio.sleep(fe.seconds + 2)
            except Exception as e:
                logger.warning(f"Error en reenvío lote ({attempt}/3): {e}")
                await asyncio.sleep(3.0)

        if chunk_ok:
            max_in_chunk = max(chunk)
            max_synced_id = max(max_synced_id, max_in_chunk)
            for cid in chunk:
                _, q, y = forward_dict[cid]
                if q and not any(it["query"] == q for it in titles_added):
                    titles_added.append({"query": q, "year": y, "type": "pelicula"})
        else:
            logger.error(f"❌ Falló el envío del lote {chunk} en '{c['nombre']}'. Se detiene para no perder sincronía.")
            break

        await asyncio.sleep(1.0)

    if chunk_ok and processed_items:
        max_synced_id = max(max_synced_id, max(item[0] for item in processed_items))

    return titles_added, max_synced_id

def normalize_series_title(title: str) -> str:
    """Normaliza estrictamente el título de una serie para comparación exacta.
    Elimina tildes/diacríticos, minúsculas, puntuación residual y espacios múltiples."""
    if not title:
        return ""
    n = unicodedata.normalize('NFKD', title)
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = n.lower().strip()
    n = re.sub(r"[._\-–—:,'\"!?()\[\]{}]+", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n

def is_valid_series_video(msg) -> bool:
    """Regla estricta TAREA 3: Verifica si el mensaje contiene video o episodio válido.
    Descarta mensajes de texto de normas, fotos decorativas, enlaces o avisos administrativos."""
    if not msg or getattr(msg, "action", None):
        return False
    if not getattr(msg, "media", None):
        return False
    fname = (msg.file.name.lower() if msg.file and hasattr(msg.file, 'name') and msg.file.name else "")
    text = (msg.text or "").lower()
    combined = f"{fname} {text}"
    is_video_ext = any(fname.endswith(ext) for ext in [".mkv", ".mp4", ".avi", ".ts", ".mov", ".m4v"])
    has_video_attr = bool(msg.file and hasattr(msg.file, 'mime_type') and 'video' in msg.file.mime_type)
    has_ep_pattern = bool(re.search(r'(?i)(?:\b[sS]\d{1,2}[eE]\d{1,2}\b|\b\d{1,2}x\d{1,2}\b|\bcap[ií]tulo\s*\d+|\btemporada\s*\d+)', combined))
    return (is_video_ext or has_video_attr or has_ep_pattern)

async def sync_channel_series(cp, c, ent_bunker, ent_prod, new_msgs):
    topic_id_filter = c.get("topic_id")
    c_prod_id = c.get("produccion_id")

    # AISLAMIENTO ESTRICTO TAREA 1: Si el destino es Series Españolas (-1004419790119),
    # jamás aceptar mensajes de otros temas y bloquear cualquier tema no español.
    if c_prod_id == -1004419790119 and topic_id_filter != 21:
        logger.warning(f"🚫 Bloqueo de seguridad: intento de volcar temas ajenos a Series Españolas en '{c['nombre']}'.")
        return [], c.get("ultimo_id_sincronizado", 0)

    # 1. FILTRO ESTRICTO TAREA 3: Mantener SOLO mensajes que contengan video o patrón de episodio.
    # Descartar normas del canal origen, anuncios, fotos decorativas o mensajes de texto.
    valid_msgs = []
    for m in new_msgs:
        if not is_valid_series_video(m):
            logger.debug(f"Descartando mensaje administrativo o sin video en '{c['nombre']}': Msg {m.id}")
            continue

        top_id = None
        if m.reply_to:
            top_id = getattr(m.reply_to, 'reply_to_top_id', None) or getattr(m.reply_to, 'reply_to_msg_id', None)
        if not top_id:
            top_id = m.id

        if topic_id_filter and top_id != topic_id_filter:
            continue

        valid_msgs.append((top_id, m))

    if not valid_msgs:
        max_seen = max([m.id for m in new_msgs], default=c.get("ultimo_id_sincronizado", 0))
        return [], max_seen

    msgs_by_topic = {}
    for top_id, m in valid_msgs:
        msgs_by_topic.setdefault(top_id, []).append(m)

    # 2. Consultar temas existentes en Producción
    p_topics = {}
    offset_date = offset_id = offset_topic = 0
    while True:
        await ensure_connected(cp, "Producción")
        res = await cp(GetForumTopicsRequest(
            peer=ent_prod, offset_date=offset_date, offset_id=offset_id, offset_topic=offset_topic, limit=100
        ))
        if not res.topics:
            break
        for t in res.topics:
            p_topics[t.title.strip()] = t.id
        if len(res.topics) < 100:
            break
        last = res.topics[-1]
        offset_date = last.date
        offset_id = last.top_message
        offset_topic = last.id

    series_added = []
    max_synced_id = c.get("ultimo_id_sincronizado", 0)

    bunker_name_norm = normalize_series_title(c.get("bunker_nombre", ""))
    banned_generic_titles = {
        "series turcas", "series espanolas", "series españolas", "general",
        "normas", "reglas", "novedades", "bienvenidos", "chat general", "temas", "videos"
    }

    for b_tid, t_msgs in msgs_by_topic.items():
        topic_title = ""
        try:
            head_msg = await cp.get_messages(ent_bunker, ids=b_tid)
            if head_msg and hasattr(head_msg, 'action') and hasattr(head_msg.action, 'title'):
                cand = head_msg.action.title.strip()
                cand_norm = normalize_series_title(cand)
                # TAREA 3: Prohibir nombres genéricos o iguales al canal origen / búnker
                if cand_norm and cand_norm not in banned_generic_titles and cand_norm != bunker_name_norm:
                    topic_title = cand
            if not topic_title:
                # Intentar extraer del nombre del archivo de video
                first_video = t_msgs[0]
                fname = first_video.file.name if first_video.file and hasattr(first_video.file, 'name') and first_video.file.name else ""
                q, _ = clean_for_search(first_video.text or "", fname)
                q_norm = normalize_series_title(q)
                if q_norm and q_norm not in banned_generic_titles and q_norm != bunker_name_norm:
                    topic_title = q
        except Exception as e:
            logger.warning(f"Error extrayendo título para topic {b_tid}: {e}")

        # TAREA 3: Si no se pudo determinar un título de serie válido o es genérico, IGNORAR Y NO CREAR TEMA
        if not topic_title or normalize_series_title(topic_title) in banned_generic_titles:
            logger.warning(f"🚫 Omitiendo topic {b_tid} en '{c['nombre']}': sin título de serie detectable o nombre genérico ('{topic_title}').")
            continue

        # Si el destino es Series Españolas, prohibir taxativamente temas turcos
        if c_prod_id == -1004419790119 and "turca" in normalize_series_title(topic_title):
            logger.warning(f"🚫 Bloqueando tema turco '{topic_title}' en canal de Series Españolas.")
            continue

        # TAREA 2: COINCIDENCIA EXACTA NORMALIZADA (PROHIBIDO coincidencia por subcadena 'in')
        norm_title = normalize_series_title(topic_title)
        p_tid = None
        for pt_title, pt_id in p_topics.items():
            if normalize_series_title(pt_title) == norm_title:
                p_tid = pt_id
                break

        is_new = False
        if not p_tid:
            is_new = True
            logger.info(f"✨ Creando nuevo tema en Producción: '{topic_title}'...")
            try:
                created = await cp(CreateForumTopicRequest(
                    peer=ent_prod,
                    title=topic_title[:120],
                    random_id=random.randint(1, 2**63 - 1)
                ))
                for u in created.updates:
                    if hasattr(u, 'id'):
                        p_tid = u.id
                        break
                    if hasattr(u, 'message') and hasattr(u.message, 'action') and hasattr(u.message.action, 'title'):
                        p_tid = u.message.id
                        break
                if p_tid:
                    p_topics[topic_title] = p_tid
            except Exception as e:
                logger.error(f"Error creando tema '{topic_title}': {e}")
                continue

        if not p_tid:
            continue

        msg_ids = [m.id for m in t_msgs if not m.action]
        if not msg_ids:
            continue

        series_ok = True
        for i in range(0, len(msg_ids), CHUNK_SIZE):
            chunk = msg_ids[i:i + CHUNK_SIZE]
            chunk_ok = False
            for attempt in range(1, 4):
                try:
                    await ensure_connected(cp, "Producción")
                    await cp(ForwardMessagesRequest(
                        from_peer=ent_bunker,
                        to_peer=ent_prod,
                        id=chunk,
                        random_id=[random.randint(1, 2**63 - 1) for _ in chunk],
                        drop_author=True,
                        top_msg_id=p_tid
                    ))
                    chunk_ok = True
                    break
                except errors.FloodWaitError as fe:
                    logger.warning(f"FloodWait de {fe.seconds}s. Esperando...")
                    await asyncio.sleep(fe.seconds + 2)
                except Exception as e:
                    logger.warning(f"Error en reenvío lote ({attempt}/3): {e}")
                    await asyncio.sleep(3.0)

            if chunk_ok:
                max_synced_id = max(max_synced_id, max(chunk))
            else:
                logger.error(f"❌ Falló reenvío del lote {chunk} en tema '{topic_title}'.")
                series_ok = False
                break

            await asyncio.sleep(1.0)

        if series_ok and is_new:
            q_clean, y_clean = clean_for_search(topic_title, "")
            series_added.append({
                "query": q_clean or topic_title,
                "year": y_clean,
                "type": "serie",
                "note": f"Nuevo tema en foro: {topic_title}"
            })

    return series_added, max_synced_id
async def send_rich_community_cards(cp, novedades):
    if not novedades:
        return
        
    logger.info("📢 Publicando fichas de estreno con carátulas en el grupo Comunidad...")
    try:
        ent_comm = await cp.get_input_entity(COMMUNITY_GROUP_ID)
        
        for c_nombre, items in novedades.items():
            for item in items[:6]:
                q = item["query"]
                y = item.get("year", "")
                mtype = item.get("type", "pelicula")
                note = item.get("note", "")
                
                meta = get_tmdb_card(q, y)
                title_display = f"{meta['title']} ({meta['year']})" if meta['year'] else meta['title']
                
                caption_lines = [
                    "✨ **¡ESTRENO DISPONIBLE EN TEVEFLIPE!** ✨",
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                    f"🎬 **{title_display}**" if mtype == "pelicula" else f"📺 **{title_display}**"
                ]
                
                if note:
                    caption_lines.append(f"📌 **Estado:** {note}")
                if meta['rating'] > 0:
                    caption_lines.append(f"⭐ **Puntuación:** {meta['rating']} / 10")
                caption_lines.append(f"📁 **Canal Oficial:** {c_nombre}")
                
                if meta['overview']:
                    caption_lines.append(f"\n📝 **Sinopsis:**\n{meta['overview']}")
                    
                caption_lines.append("\n🍿 _¡Ya disponible para ver y disfrutar en TeVeFLIPE!_")
                caption_text = "\n".join(caption_lines)
                
                if meta['poster_url']:
                    try:
                        img_res = requests.get(meta['poster_url'], timeout=6)
                        if img_res.status_code == 200:
                            img_io = io.BytesIO(img_res.content)
                            img_io.name = "poster.jpg"
                            await cp.send_file(
                                entity=ent_comm,
                                file=img_io,
                                caption=caption_text,
                                reply_to=COMMUNITY_TOPIC_ID,
                                parse_mode="markdown"
                            )
                            logger.info(f"  ✅ Ficha con carátula enviada para '{title_display}'")
                            await asyncio.sleep(2.0)
                            continue
                    except Exception as pe:
                        logger.warning(f"Aviso descargando póster TMDB: {pe}")
                        
                await cp.send_message(
                    entity=ent_comm,
                    message=caption_text,
                    reply_to=COMMUNITY_TOPIC_ID,
                    parse_mode="markdown"
                )
                logger.info(f"  ✅ Ficha en texto enviada para '{title_display}'")
                await asyncio.sleep(1.5)
    except Exception as e:
        logger.error(f"Error enviando avisos a la comunidad: {e}")

async def main():
    logger.info("=" * 80)
    logger.info("🛰️ INICIANDO ESCÁNER INTELIGENTE DE NOVEDADES BÚNKERS ➔ PRODUCCIÓN")
    logger.info("=" * 80)
    
    if not SESSION_PROD:
        logger.error("❌ ERROR: SESSION_PROD no configurada.")
        sys.exit(1)
        
    cp = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)
    await cp.start()
    
    me_p = await cp.get_me()
    logger.info(f"Conectado como: {me_p.first_name} (ID: {me_p.id})")
    
    canales = load_json(MAP_FILE, default=[])
    if not canales:
        logger.error(f"❌ No se encontró o está vacío {MAP_FILE}.")
        sys.exit(1)
        
    novedades_detectadas = {}
    
    for c in canales:
        if not c.get("activo", True) or not c.get("produccion_id") or not c.get("bunker_id"):
            continue
            
        c_nombre = c["nombre"]
        b_id = c["bunker_id"]
        last_id = c.get("ultimo_id_sincronizado", 0)
        is_forum = c.get("is_forum", False)
        
        try:
            ent_bunker = await cp.get_input_entity(b_id)
            topic_id = c.get("topic_id")
            filtro_intel = c.get("filtro_inteligente")

            # Si el canal lee de un topic específico, comprobar actividad SOLO en ese topic
            if topic_id:
                latest = await cp.get_messages(ent_bunker, reply_to=topic_id, limit=1)
            else:
                latest = await cp.get_messages(ent_bunker, limit=1)

            current_top = latest[0].id if latest else 0
            
            if current_top <= last_id:
                continue
                
            logger.info(f"🔔 Detectada actividad en '{c_nombre}' (IDs {last_id} ➔ {current_top})")
            
            iter_kwargs = {"min_id": last_id, "reverse": True}
            if topic_id:
                iter_kwargs["reply_to"] = topic_id
                
            new_msgs = [m async for m in cp.iter_messages(ent_bunker, **iter_kwargs) 
                        if not m.action and (m.media or m.text)]
                        
            if filtro_intel == "documentales":
                new_msgs = [m for m in new_msgs if is_valid_documentary(m)]
                
            if not new_msgs:
                c["ultimo_id_sincronizado"] = current_top
                continue
                
            ent_prod = await cp.get_input_entity(c["produccion_id"])
            if not is_forum:
                items, new_last_id = await sync_channel_peliculas(cp, c, ent_bunker, ent_prod, new_msgs)
            else:
                items, new_last_id = await sync_channel_series(cp, c, ent_bunker, ent_prod, new_msgs)
                
            if new_last_id > last_id:
                c["ultimo_id_sincronizado"] = new_last_id
            if items:
                novedades_detectadas[c_nombre] = items
                logger.info(f"✅ {len(items)} títulos procesados exitosamente en '{c_nombre}'.")
                
        except Exception as e:
            logger.error(f"Error procesando canal '{c_nombre}': {e}")
            
    save_json(MAP_FILE, canales)
    
    if novedades_detectadas:
        logger.info("\n🎉 Novedades detectadas en esta revisión. Enviando fichas con carátula...")
        await send_rich_community_cards(cp, novedades_detectadas)
    else:
        logger.info("\n☕ Sin novedades en ningún búnker. Todo el catálogo se encuentra al día.")
        
    await cp.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
