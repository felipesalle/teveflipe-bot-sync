import os
import sys
import json
import asyncio
import logging
import random
import re
import io
import unicodedata
import requests
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import (
    ForwardMessagesRequest,
    CreateForumTopicRequest,
    GetForumTopicsRequest
)

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("SyncMaestroUniversal")

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_BUNKER = os.getenv("SESSION_BUNKER") or ""
SESSION_PROD = os.getenv("SESSION_PROD") or ""
COMMUNITY_GROUP_ID = int(os.getenv("COMMUNITY_GROUP_ID", "-1003990716596"))
COMMUNITY_TOPIC_ID = int(os.getenv("COMMUNITY_TOPIC_ID", "22"))
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "2b7cd7b237fe99884613b230a910a09c")
MAP_FILE = "canales_map.json"
INVENTARIO_FILE = "inventario_produccion.json"
CHUNK_SIZE = 5

BANNED_EXTENSIONS = ('.zip', '.tar', '.gz', '.iso', '.torrent', '.txt', '.nfo', '.exe')
VIDEO_EXTENSIONS = ('.mkv', '.mp4', '.avi', '.ts', '.mov', '.m4v', '.webm', '.flv', '.wmv', '.rar', '.7z')

SERIES_EPISODE_REGEX = re.compile(
    r'(?i)(?:\b[sS](\d{1,2})[eE](\d{1,2})\b|\b(\d{1,2})x(\d{1,2})\b|\bcap[ií]tulo\s*(\d+)|\bepisodio\s*(\d+))'
)
SERIES_CLEAN_REGEX = re.compile(
    r'(?i)[_\s\.\-]*(?:S\d+E\d+|\d+x\d+|Cap[ií]tulo\s*\d+|Temporada\s*\d+|Season\s*\d+|Episodio\s*\d+|T\d+|S\d+|Cap\s*\d+).*$'
)

NON_DOC_KEYWORDS = [
    "cuarto milenio", "horizonte", "el hormiguero", "la resistencia", "la revuelta",
    "el chiringuito", "masterchef", "supervivientes", "gran hermano", "gh vip",
    "la isla de las tentaciones", "first dates", "salvame", "deluxe", "fiesta",
    "la ruleta de la suerte", "pasapalabra", "tu cara me suena", "got talent",
    "la voz", "operacion triunfo", "ot 20", "pesadilla en la cocina", "equipodeinvestigacion",
    "equipo de investigacion", "la sexta noche", "la sexta columna", "al rojo vivo",
    "espejo publico", "el programa de ana rosa", "vamos a ver", "y ahora sonsoles",
    "cuatro al dia", "telediario", "antena 3 noticias", "informativos telecinco"
]

DOC_KEYWORDS = [
    "documental", "docu", "bbc", "national geographic", "nat geo", "discovery",
    "history channel", "netflix doc", "biografia", "naturaleza", "planeta",
    "universo", "historia de", "la segunda guerra", "la primera guerra",
    "secretos de", "misterios de", "vida salvaje", "fauna", "oceano", "dinosaurios",
    "cosmos", "apolo", "nasa", "expedicion", "arqueologia", "imperio", "civilizacion",
    "egipto", "roma", "grecia", "ciencia", "origen de"
]

def is_user_excluded(title: str, fname: str) -> bool:
    t = f"{title} {fname}".lower()
    if "isla de las tentaciones" in t or "tentaciones" in t:
        return True
    if "la voz" in t or "la_voz" in t:
        return True
    return False

def is_valid_documentary(text: str, fname: str) -> bool:
    combined = f"{text or ''} {fname or ''}".lower()
    for kw in NON_DOC_KEYWORDS:
        if kw in combined:
            return False
    for kw in DOC_KEYWORDS:
        if kw in combined:
            return True
    return False

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

def clean_series_title(text: str, filename: str) -> str:
    raw = (text or "").strip()
    if not raw and filename:
        raw = os.path.splitext(filename)[0]
    
    line = raw.split("\n")[0].strip()
    line = re.sub(r"^[🎬📺🎥🎞️👶💥🥢✨📼🌍🎸🪐\[\(#\s*]+", "", line)
    line = re.sub(r"\[.*?\]|\(.*?\)", "", line)
    line = SERIES_CLEAN_REGEX.sub("", line)
    line = re.sub(r"(?i)\b(1080p|720p|4k|2160p|bluray|web-dl|webdl|webrip|hdrip|x264|x265|hevc|aac|dts|dual|latino|castellano|subtitulado|sub|completa).*$", "", line)
    line = re.sub(r"[._\-–—]", " ", line)
    line = re.sub(r"\s+", " ", line).strip()
    return line

def is_banned_file(fname: str) -> bool:
    fn = (fname or "").lower().strip()
    return any(fn.endswith(ext) for ext in BANNED_EXTENSIONS)

def is_video_or_multipart(fname: str, mime_type: str = "") -> bool:
    fn = (fname or "").lower().strip()
    if is_banned_file(fn):
        return False
    if any(fn.endswith(ext) for ext in VIDEO_EXTENSIONS):
        return True
    if re.search(r'\.(?:part\d+\.rar|7z\.\d+|\d{2,4})$', fn):
        return True
    if mime_type and 'video' in mime_type.lower():
        return True
    return False

def is_series_episode(text: str, filename: str) -> bool:
    content = f"{text or ''} {filename or ''}"
    return bool(SERIES_EPISODE_REGEX.search(content))

def extract_episode_tag(text: str, filename: str) -> str:
    combined = f"{text or ''} {filename or ''}"
    m = SERIES_EPISODE_REGEX.search(combined)
    if m:
        if m.group(1) and m.group(2):
            return f"s{int(m.group(1)):02d}e{int(m.group(2)):02d}"
        if m.group(3) and m.group(4):
            return f"s{int(m.group(3)):02d}e{int(m.group(4)):02d}"
        if m.group(5):
            return f"cap_{int(m.group(5)):03d}"
        if m.group(6):
            return f"cap_{int(m.group(6)):03d}"
    return ""

async def get_tmdb_card(query: str, year: str = "", is_series: bool = False):
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
        url = "https://api.themoviedb.org/3/search/tv" if is_series else "https://api.themoviedb.org/3/search/movie"
        params = {"api_key": TMDB_API_KEY, "query": query, "language": "es-ES"}
        if year and not is_series:
            params["year"] = year
        res = requests.get(url, params=params, timeout=5).json()
        results = res.get("results", [])
        if not results and year and not is_series:
            params.pop("year", None)
            res = requests.get(url, params=params, timeout=5).json()
            results = res.get("results", [])
            
        if results:
            best = results[0]
            title = best.get("name" if is_series else "title") or query
            date_str = best.get("first_air_date" if is_series else "release_date") or ""
            res_year = date_str[:4] if date_str else year
            poster_path = best.get("poster_path")
            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
            return {
                "title": title,
                "year": res_year,
                "overview": (best.get("overview", "") or "").strip(),
                "poster_url": poster_url,
                "rating": round(best.get("vote_average", 0.0), 1)
            }
    except Exception as e:
        logger.warning(f"Aviso consultando TMDB para '{query}': {e}")
    return default_meta

async def send_community_announcement(client, title: str, category: str, is_series: bool = False, year: str = ""):
    try:
        meta = await get_tmdb_card(title, year=year, is_series=is_series)
        caption_lines = [
            f"🎬 **¡Novedad Disponible en TeVeFLIPE!**" if not is_series else f"📺 **¡Nueva Serie en TeVeFLIPE!**",
            "",
            f"📌 **Título:** {meta['title']}",
            f"📁 **Categoría:** {category.capitalize()}"
        ]
        if meta.get("year"):
            caption_lines.append(f"📅 **Año:** {meta['year']}")
        if meta.get("rating"):
            caption_lines.append(f"⭐ **Valoración:** {meta['rating']:.1f}/10")
        if meta.get("overview"):
            overview = meta["overview"]
            if len(overview) > 300:
                overview = overview[:300] + "..."
            caption_lines.append(f"\n📖 **Sinopsis:**\n{overview}")
        caption_lines.append("\n🍿 _¡Disponible ahora en tus canales y en la app!_")
        caption = "\n".join(caption_lines)

        if meta.get("poster_url"):
            try:
                img_data = requests.get(meta["poster_url"], timeout=5).content
                file_obj = io.BytesIO(img_data)
                file_obj.name = "poster.jpg"
                await client.send_file(
                    COMMUNITY_GROUP_ID,
                    file_obj,
                    caption=caption,
                    reply_to=COMMUNITY_TOPIC_ID,
                    parse_mode="markdown"
                )
                logger.info(f"📢 Ficha publicada con carátula en Comunidad: {meta['title']}")
                return
            except Exception as e_img:
                logger.warning(f"Error subiendo poster a Comunidad: {e_img}")

        await client.send_message(
            COMMUNITY_GROUP_ID,
            caption,
            reply_to=COMMUNITY_TOPIC_ID,
            parse_mode="markdown"
        )
        logger.info(f"📢 Ficha publicada en texto en Comunidad: {meta['title']}")
    except Exception as e:
        logger.warning(f"No se pudo enviar anuncio a Comunidad para '{title}': {e}")

async def relay_forward_chunk(cb, cp, me_b, me_p, ent_bunker, ent_prod, chunk, top_msg_id=None):
    # Paso 1: CB reenvía a CP en privado
    await cb(ForwardMessagesRequest(
        from_peer=ent_bunker,
        to_peer=await cb.get_input_entity(me_p.id),
        id=chunk,
        random_id=[random.randint(1, 2**63 - 1) for _ in chunk],
        drop_author=True
    ))
    await asyncio.sleep(1.0)
    
    # Obtener IDs temporales en CP
    received = [m.id async for m in cp.iter_messages(me_b.id, limit=len(chunk))]
    received.reverse()
    
    # Paso 2: CP reenvía a Producción
    req_kwargs = {
        "from_peer": await cp.get_input_entity(me_b.id),
        "to_peer": ent_prod,
        "id": received,
        "random_id": [random.randint(1, 2**63 - 1) for _ in received],
        "drop_author": True
    }
    if top_msg_id:
        req_kwargs["top_msg_id"] = top_msg_id
        
    await cp(ForwardMessagesRequest(**req_kwargs))
    
    # Paso 3: Limpiar privados temporales
    try:
        await cp.delete_messages(me_b.id, received)
    except Exception:
        pass

async def audit_channel(cb, cp, c, inventario_canales):
    c_id = c["id"]
    c_nombre = c["nombre"]
    b_id = c["bunker_id"]
    p_id = c.get("produccion_id")
    last_id = c.get("ultimo_id_sincronizado", 0)
    topic_id = c.get("topic_id")
    is_forum = c.get("is_forum", False)
    filtro_intel = c.get("filtro_inteligente")

    # Cargar huellas de Producción (de inventario y/o lectura reciente)
    inv_data = inventario_canales.get(c_id, {})
    prod_filenames = set(inv_data.get("filenames", []))
    prod_fps = set(inv_data.get("fingerprints", []))
    prod_temas = inv_data.get("temas", {})

    try:
        ent_bunker = await cb.get_input_entity(b_id)
        if topic_id:
            latest = await cb.get_messages(ent_bunker, reply_to=topic_id, limit=1)
        else:
            latest = await cb.get_messages(ent_bunker, limit=1)
        current_top = latest[0].id if latest else 0

        if current_top <= last_id:
            return {"nombre": c_nombre, "estado": "AL_DIA", "last_id": last_id, "current_top": current_top, "novedades": []}

        # Leer mensajes nuevos
        iter_kwargs = {"min_id": last_id, "reverse": True}
        if topic_id:
            iter_kwargs["reply_to"] = topic_id

        bunker_msgs = [m async for m in cb.iter_messages(ent_bunker, **iter_kwargs)
                       if not m.action and (m.media or m.text)]

        novedades_reales = []
        for m in bunker_msgs:
            fn = getattr(getattr(m, 'file', None), 'name', '') or ""
            txt = m.text or ""
            fn_clean = fn.lower().strip()

            if is_banned_file(fn):
                continue
            if is_user_excluded(txt, fn):
                continue
            if filtro_intel == "documentales" and not is_valid_documentary(txt, fn):
                continue

            # Comprobar contra Producción
            if not is_forum:
                if not is_video_or_multipart(fn, getattr(getattr(m, 'file', None), 'mime_type', '')):
                    continue
                if is_series_episode(txt, fn):
                    continue

                q, y = clean_for_search(txt, fn)
                norm_q = normalize_text(q)
                fp = f"{norm_q} {y}".strip()

                if fn_clean and fn_clean in prod_filenames:
                    continue
                if fp and fp in prod_fps:
                    continue

                novedades_reales.append({
                    "msg_id": m.id,
                    "titulo": q or fn,
                    "filename": fn,
                    "size_mb": f"{(getattr(m.file, 'size', 0) / (1024*1024)):.1f} MB" if m.file else ""
                })
            else:
                # Supergrupos de series
                if not is_video_or_multipart(fn, getattr(getattr(m, 'file', None), 'mime_type', '')):
                    continue

                ep_tag = extract_episode_tag(txt, fn)
                series_name = clean_series_title(txt, fn)
                norm_series = normalize_text(series_name)
                if not norm_series or norm_series in ("sticker", "video", "audio", "archivo", "varios"):
                    continue

                # Si el archivo exacto ya está en el inventario del foro
                if fn_clean and fn_clean in prod_filenames:
                    continue
                if norm_series in prod_temas:
                    tema_info = prod_temas[norm_series]
                    if ep_tag and ep_tag in tema_info.get("episodes", []):
                        continue
                    if fn_clean and fn_clean in tema_info.get("files", []):
                        continue

                novedades_reales.append({
                    "msg_id": m.id,
                    "titulo": series_name or fn,
                    "episode": ep_tag,
                    "filename": fn,
                    "size_mb": f"{(getattr(m.file, 'size', 0) / (1024*1024)):.1f} MB" if m.file else ""
                })

        return {
            "nombre": c_nombre,
            "estado": "NOVEDADES" if novedades_reales else "AL_DIA",
            "last_id": last_id,
            "current_top": current_top,
            "novedades": novedades_reales
        }
    except Exception as e:
        logger.error(f"Error auditando '{c_nombre}': {e}")
        return {"nombre": c_nombre, "estado": "ERROR", "error": str(e), "last_id": last_id, "novedades": []}

async def sync_channel(cb, cp, me_b, me_p, c, inventario_canales):
    c_id = c["id"]
    c_nombre = c["nombre"]
    b_id = c["bunker_id"]
    p_id = c.get("produccion_id")
    last_id = c.get("ultimo_id_sincronizado", 0)
    topic_id = c.get("topic_id")
    is_forum = c.get("is_forum", False)
    categoria = c.get("categoria", "general")
    filtro_intel = c.get("filtro_inteligente")

    logger.info(f"Procesando canal: {c_nombre} (Puntero: {last_id})")
    
    ent_bunker = await cb.get_input_entity(b_id)
    ent_prod = await cp.get_input_entity(p_id)

    iter_kwargs = {"min_id": last_id, "reverse": True}
    if topic_id:
        iter_kwargs["reply_to"] = topic_id

    bunker_msgs = [m async for m in cb.iter_messages(ent_bunker, **iter_kwargs)
                   if not m.action and (m.media or m.text)]

    if not bunker_msgs:
        logger.info(f"  ☕ Sin nuevos mensajes en Búnker para {c_nombre}.")
        return 0

    inv_data = inventario_canales.get(c_id, {})
    prod_filenames = set(inv_data.get("filenames", []))
    prod_fps = set(inv_data.get("fingerprints", []))
    prod_temas = inv_data.get("temas", {})

    # Leer historial fresco de los últimos 200 de producción para blindaje absoluto
    try:
        if not is_forum:
            async for pm in cp.iter_messages(ent_prod, limit=200):
                if pm.file and getattr(pm.file, 'name', None):
                    prod_filenames.add(pm.file.name.lower().strip())
    except Exception as eh:
        logger.warning(f"Aviso leyendo historial reciente de Producción: {eh}")

    highest_id = last_id
    synchronized_count = 0

    if not is_forum:
        current_chunk = []
        titles_forwarded = []

        for m in bunker_msgs:
            highest_id = max(highest_id, m.id)
            fn = getattr(getattr(m, 'file', None), 'name', '') or ""
            txt = m.text or ""
            fn_clean = fn.lower().strip()

            if is_banned_file(fn):
                continue
            if is_user_excluded(txt, fn):
                continue
            if filtro_intel == "documentales" and not is_valid_documentary(txt, fn):
                continue
            if not is_video_or_multipart(fn, getattr(getattr(m, 'file', None), 'mime_type', '')):
                continue
            if is_series_episode(txt, fn):
                continue

            q, y = clean_for_search(txt, fn)
            norm_q = normalize_text(q)
            fp = f"{norm_q} {y}".strip()

            # Duplicado check
            if fn_clean and fn_clean in prod_filenames:
                logger.info(f"  ⏩ Omitiendo '{fn}': ya existe en Producción.")
                continue
            if fp and fp in prod_fps:
                logger.info(f"  ⏩ Omitiendo '{q} ({y})': título ya existente en Producción.")
                continue

            current_chunk.append(m.id)
            if q:
                titles_forwarded.append((q, y))
            if fn_clean:
                prod_filenames.add(fn_clean)
            if fp:
                prod_fps.add(fp)

            if len(current_chunk) >= CHUNK_SIZE:
                logger.info(f"  🚀 Reenviando bloque de {len(current_chunk)} archivos a '{c_nombre}'...")
                await relay_forward_chunk(cb, cp, me_b, me_p, ent_bunker, ent_prod, current_chunk)
                synchronized_count += len(current_chunk)
                current_chunk = []
                await asyncio.sleep(2.0)

        if current_chunk:
            logger.info(f"  🚀 Reenviando bloque residual de {len(current_chunk)} archivos a '{c_nombre}'...")
            await relay_forward_chunk(cb, cp, me_b, me_p, ent_bunker, ent_prod, current_chunk)
            synchronized_count += len(current_chunk)
            await asyncio.sleep(2.0)

        # Avisos TMDB a la Comunidad
        for t, y in titles_forwarded:
            await send_community_announcement(cp, t, categoria, is_series=False, year=y)
            await asyncio.sleep(1.5)

    else:
        # Modo Series / Foros
        # Recuperar topics de Producción en vivo
        live_topics = {}
        try:
            res_t = await cp(GetForumTopicsRequest(peer=ent_prod, offset_date=None, offset_id=0, offset_topic=0, limit=100))
            for t in (res_t.topics or []):
                live_topics[normalize_text(t.title)] = t.id
        except Exception as e_lt:
            logger.warning(f"Aviso leyendo topics de '{c_nombre}': {e_lt}")

        # Agrupar mensajes del Búnker por serie
        series_batches = {}
        for m in bunker_msgs:
            highest_id = max(highest_id, m.id)
            fn = getattr(getattr(m, 'file', None), 'name', '') or ""
            txt = m.text or ""
            fn_clean = fn.lower().strip()

            if is_banned_file(fn):
                continue
            if is_user_excluded(txt, fn):
                continue
            if not is_video_or_multipart(fn, getattr(getattr(m, 'file', None), 'mime_type', '')):
                continue

            series_name = clean_series_title(txt, fn)
            norm_s = normalize_text(series_name)
            if not norm_s or norm_s in ("sticker", "video", "audio", "archivo", "varios"):
                logger.info(f"  ⏩ Omitiendo mensaje {m.id}: nombre de serie inválido ('{series_name}')")
                continue

            if norm_s not in series_batches:
                series_batches[norm_s] = {"display_name": series_name or norm_s, "messages": []}
            series_batches[norm_s]["messages"].append(m)

        for norm_s, sdata in series_batches.items():
            display_name = sdata["display_name"]
            msgs = sdata["messages"]

            # Obtener o crear topic en Producción con búsqueda tolerante
            topic_dest_id = live_topics.get(norm_s)
            if not topic_dest_id:
                for lt_name, lt_id in live_topics.items():
                    if lt_name == norm_s or (len(norm_s) > 4 and norm_s in lt_name) or (len(lt_name) > 4 and lt_name in norm_s):
                        topic_dest_id = lt_id
                        break

            is_new_topic = False
            if not topic_dest_id:
                try:
                    logger.info(f"  ✨ Creando tema nuevo en foro '{c_nombre}': '{display_name}'")
                    created_t = await cp(CreateForumTopicRequest(
                        peer=ent_prod,
                        title=display_name[:120],
                        icon_color=0x6FB9F0
                    ))
                    topic_dest_id = created_t.updates[0].id if hasattr(created_t, 'updates') else created_t.id
                    live_topics[norm_s] = topic_dest_id
                    is_new_topic = True
                    await asyncio.sleep(1.0)
                except Exception as ect:
                    logger.warning(f"No se pudo crear topic '{display_name}': {ect}")
                    topic_dest_id = None

            # Reenviar mensajes en chunks
            msg_ids = [m.id for m in msgs]
            for i in range(0, len(msg_ids), CHUNK_SIZE):
                chunk = msg_ids[i:i+CHUNK_SIZE]
                await relay_forward_chunk(cb, cp, me_b, me_p, ent_bunker, ent_prod, chunk, top_msg_id=topic_dest_id)
                synchronized_count += len(chunk)
                await asyncio.sleep(2.0)

            if is_new_topic:
                await send_community_announcement(cp, display_name, categoria, is_series=True)
                await asyncio.sleep(1.5)

    c["ultimo_id_sincronizado"] = highest_id
    logger.info(f"✅ Sincronización en '{c_nombre}' completada. {synchronized_count} mensajes procesados. Nuevo puntero: {highest_id}")
    return synchronized_count

def load_channels_merged() -> list:
    canales = []
    if os.path.exists(MAP_FILE):
        try:
            with open(MAP_FILE, "r", encoding="utf-8") as f:
                canales = json.load(f)
        except Exception as e:
            logger.warning(f"Aviso leyendo {MAP_FILE}: {e}")

    prod_map = {c.get("produccion_id"): c for c in canales if c.get("produccion_id")}

    # Enriquecer dinámicamente con Firebase Realtime Database (channels.json)
    try:
        url = "https://teveflipe-default-rtdb.firebaseio.com/channels.json"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            rtdb_data = res.json() or {}
            for k, val in rtdb_data.items():
                if not isinstance(val, dict):
                    continue
                p_id = val.get("id") or int(k)
                b_id = val.get("bunker_id")
                is_active = val.get("active", True)
                name = val.get("name")
                invite = val.get("inviteLink", "")
                cat = val.get("category", "general")
                is_forum = bool(val.get("isForum", False))

                if p_id in prod_map:
                    # Respetar activación/pausa y nombre desde la landing page, pero si está excluido localmente, mantenerlo desactivado
                    if prod_map[p_id].get("activo") is False:
                        pass
                    else:
                        prod_map[p_id]["activo"] = is_active
                    if name:
                        prod_map[p_id]["nombre"] = name
                    if invite:
                        prod_map[p_id]["invite_link"] = invite
                    if b_id:
                        prod_map[p_id]["bunker_id"] = b_id
                elif b_id:
                    # Canal nuevo agregado desde la landing page con Búnker asignado
                    nuevo = {
                        "id": f"canal_{abs(p_id)}",
                        "nombre": name or f"Canal {p_id}",
                        "bunker_id": b_id,
                        "produccion_id": p_id,
                        "invite_link": invite,
                        "categoria": cat,
                        "is_forum": is_forum,
                        "ultimo_id_sincronizado": 0,
                        "activo": is_active
                    }
                    canales.append(nuevo)
                    prod_map[p_id] = nuevo
                    logger.info(f"🌐 Canal nuevo detectado desde Firebase Landing: '{name}' (Búnker: {b_id} ➔ Prod: {p_id})")
    except Exception as fe:
        logger.warning(f"Aviso sincronizando canales desde Firebase RTDB: {fe}")

    return canales

async def main():
    mode = "--sync" if "--sync" in sys.argv else "--audit"
    print("=" * 70)
    print(f"🛰️ MOTOR MAESTRO UNIVERSAL DE SINCRONIZACIÓN BÚNKERS ➔ PRODUCCIÓN")
    print(f"   Modo de ejecución: {mode.upper()}")
    print("=" * 70)

    if not SESSION_BUNKER or not SESSION_PROD:
        logger.error("❌ ERROR: SESSION_BUNKER y SESSION_PROD deben estar ambas configuradas.")
        sys.exit(1)

    cb = TelegramClient(StringSession(SESSION_BUNKER), API_ID, API_HASH)
    cp = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)

    await cb.start()
    await cp.start()

    me_b = await cb.get_me()
    me_p = await cp.get_me()
    logger.info(f"Cuenta Búnker (Lector): {me_b.first_name} (ID: {me_b.id})")
    logger.info(f"Cuenta Producción (Admin): {me_p.first_name} (ID: {me_p.id})")

    logger.info("Precargando diálogos en ambas cuentas...")
    await cb.get_dialogs(limit=None)
    await cp.get_dialogs(limit=None)

    canales = load_channels_merged()

    inventario = {}
    if os.path.exists(INVENTARIO_FILE):
        try:
            with open(INVENTARIO_FILE, "r", encoding="utf-8") as f:
                inventario = json.load(f)
        except Exception:
            inventario = {}

    inv_canales = inventario.get("canales", {})

    if mode == "--audit":
        logger.info("\n🔍 EJECUTANDO AUDITORÍA ANTI-FALSOS POSITIVOS...")
        reporte = []
        for c in canales:
            if not c.get("activo", True) or not c.get("produccion_id") or not c.get("bunker_id"):
                continue
            rep = await audit_channel(cb, cp, c, inv_canales)
            reporte.append(rep)

        print("\n" + "=" * 70)
        print("📋 INFORME DE AUDITORÍA DE NOVEDADES REALES (ANTI-DUPLICADOS)")
        print("=" * 70)
        con_novedades = [r for r in reporte if r["estado"] == "NOVEDADES"]
        al_dia = [r for r in reporte if r["estado"] == "AL_DIA"]
        con_error = [r for r in reporte if r["estado"] == "ERROR"]

        if con_novedades:
            print(f"\n🔔 SE ENCONTRARON NOVEDADES REALES EN {len(con_novedades)} CANALES:\n")
            for r in con_novedades:
                print(f"📁 {r['nombre']} (Puntero: {r['last_id']} ➔ Búnker: {r['current_top']})")
                print(f"   Archivos pendientes reales: {len(r['novedades'])}")
                for nov in r["novedades"][:10]:
                    sz = f" [{nov['size_mb']}]" if nov['size_mb'] else ""
                    print(f"   ↳ 🎬 [ID {nov['msg_id']}] {nov['titulo']}{sz}")
                if len(r["novedades"]) > 10:
                    print(f"   ↳ ... y {len(r['novedades']) - 10} más.")
                print()
        else:
            print("\n✨ ¡Todos los canales están al día! Cero novedades falsas detectadas.")

        if al_dia:
            print(f"\n👌 Canales al día ({len(al_dia)}):")
            for r in al_dia:
                print(f"   • {r['nombre']} (ID: {r['last_id']})")

        if con_error:
            print(f"\n⚠️ Canales con incidencia ({len(con_error)}):")
            for r in con_error:
                print(f"   • {r['nombre']}: {r.get('error')}")

    elif mode == "--sync":
        logger.info("\n🚀 EJECUTANDO SINCRONIZACIÓN AUTOMÁTICA UNIVERSAL...")
        total_sincronizados = 0
        for c in canales:
            if not c.get("activo", True) or not c.get("produccion_id") or not c.get("bunker_id"):
                continue
            try:
                count = await sync_channel(cb, cp, me_b, me_p, c, inv_canales)
                total_sincronizados += count
            except Exception as e_ch:
                logger.error(f"Error sincronizando canal '{c['nombre']}': {e_ch}")

        with open(MAP_FILE, "w", encoding="utf-8") as f:
            json.dump(canales, f, indent=2, ensure_ascii=False)
        logger.info(f"\n🎉 Sincronización finalizada con éxito. Total mensajes retransmitidos: {total_sincronizados}")

    await cb.disconnect()
    await cp.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
