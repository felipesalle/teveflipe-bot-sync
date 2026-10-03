import asyncio
import io
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
    GetForumTopicsRequest
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
SESSION_BUNKER = os.getenv("SESSION_BUNKER") or ""
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

async def ensure_clients(cb: TelegramClient, cp: TelegramClient):
    await ensure_connected(cb, "Búnker")
    await ensure_connected(cp, "Producción")

def clean_for_search(text: str, filename: str) -> tuple[str, str]:
    """Extrae un título limpio y el año para buscar en TMDb."""
    raw = filename or text or ""
    raw = os.path.splitext(raw)[0]
    
    # Extraer año
    y_match = re.search(r'\b(19\d\d|20\d\d)\b', raw)
    year = y_match.group(1) if y_match else ""
    
    # Si hay año, recortar lo que viene después de año
    if y_match:
        raw = raw[:y_match.end()]
        
    # Reemplazar caracteres especiales
    clean = re.sub(r'[\._\-+]', ' ', raw)
    # Limpiar etiquetas comunes de ripeo
    clean = re.sub(r'(?i)\b(webdl|web-dl|1080p|720p|4k|x264|x265|hevc|eac3|dts|aac|dual|castellano|latino|cine|completo|completos|repack|pelicula|capitulo)\b', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean or "Estreno", year

def get_tmdb_card(query: str, year: str = ""):
    """Consulta TMDb para obtener póster oficial, título formateado, sinopsis y puntuación."""
    try:
        url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&language=es-ES&query={requests.utils.quote(query)}"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            results = r.json().get("results", [])
            if results:
                best = results[0]
                if year:
                    for res in results[:3]:
                        date = res.get("release_date") or res.get("first_air_date") or ""
                        if date.startswith(year):
                            best = res
                            break
                            
                name = best.get("title") or best.get("name") or query
                date = best.get("release_date") or best.get("first_air_date") or ""
                y = date[:4] if date else year
                overview = best.get("overview") or ""
                rating = best.get("vote_average", 0)
                poster = best.get("poster_path")
                poster_url = f"https://image.tmdb.org/t/p/w500{poster}" if poster else None
                
                return {
                    "title": name,
                    "year": y,
                    "overview": overview[:240] + ("..." if len(overview) > 240 else ""),
                    "rating": round(rating, 1),
                    "poster_url": poster_url
                }
    except Exception as e:
        logger.warning(f"Error buscando '{query}' en TMDb: {e}")
        
    return {
        "title": query,
        "year": year,
        "overview": "",
        "rating": 0,
        "poster_url": None
    }

async def sync_channel_peliculas(cb, cp, c, prod_user, bunker_user, ent_bunker, ent_prod, new_msgs):
    msg_ids = [m.id for m in new_msgs]
    titles_added = []
    
    for i in range(0, len(msg_ids), CHUNK_SIZE):
        chunk = msg_ids[i:i + CHUNK_SIZE]
        for attempt in range(1, 4):
            try:
                await ensure_clients(cb, cp)
                
                # A. Bunker -> DM Prod
                fwd_res = await cb.forward_messages(
                    entity=prod_user,
                    messages=chunk,
                    from_peer=ent_bunker,
                    drop_author=True
                )
                b_fwd = [m.id for m in fwd_res] if isinstance(fwd_res, list) else [fwd_res.id]
                
                # B. Prod recibe de DM
                recv = await cp.get_messages(bunker_user, limit=len(b_fwd))
                if not isinstance(recv, list):
                    recv = [recv]
                p_recv = [m.id for m in reversed(recv) if not m.action]
                
                # C. Prod reenvía al canal oficial
                if p_recv:
                    r_ids = [random.randint(1, 2**63 - 1) for _ in p_recv]
                    await cp(ForwardMessagesRequest(
                        from_peer=await cp.get_input_entity(bunker_user),
                        to_peer=ent_prod,
                        id=p_recv,
                        random_id=r_ids,
                        drop_author=True
                    ))
                
                # D. Limpieza de DM
                try:
                    await cb.delete_messages(prod_user, b_fwd, revoke=True)
                    await cp.delete_messages(bunker_user, p_recv, revoke=True)
                except Exception:
                    pass
                
                break
            except errors.FloodWaitError as fe:
                logger.warning(f"FloodWait de {fe.seconds}s. Esperando...")
                await asyncio.sleep(fe.seconds + 2)
            except Exception as e:
                logger.warning(f"Error en reenvío lote ({attempt}/3): {e}")
                await asyncio.sleep(4.0)
                await ensure_clients(cb, cp)
        
        await asyncio.sleep(2.0)
        
    for m in new_msgs:
        fname = m.file.name if m.file and m.file.name else ""
        q, y = clean_for_search(m.text or "", fname)
        if q and not any(it["query"] == q for it in titles_added):
            titles_added.append({"query": q, "year": y, "type": "pelicula"})
            
    return titles_added

async def sync_channel_series(cb, cp, c, prod_user, bunker_user, ent_bunker, ent_prod, new_msgs):
    msgs_by_topic = {}
    for m in new_msgs:
        top_id = None
        if m.reply_to:
            top_id = getattr(m.reply_to, 'reply_to_top_id', None) or getattr(m.reply_to, 'reply_to_msg_id', None)
        if not top_id:
            top_id = m.id
        msgs_by_topic.setdefault(top_id, []).append(m)
        
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
            p_topics[t.title.strip().lower()] = t.id
        if len(res.topics) < 100:
            break
        last = res.topics[-1]
        offset_date = last.date
        offset_id = last.top_message
        offset_topic = last.id
        
    series_added = []
    
    for b_tid, t_msgs in msgs_by_topic.items():
        topic_title = f"Tema {b_tid}"
        try:
            head_msg = await cb.get_messages(ent_bunker, ids=b_tid)
            if head_msg and hasattr(head_msg, 'action') and hasattr(head_msg.action, 'title'):
                topic_title = head_msg.action.title.strip()
            elif head_msg and head_msg.file and head_msg.file.name:
                q, _ = clean_for_search("", head_msg.file.name)
                topic_title = q
            elif head_msg and head_msg.text:
                q, _ = clean_for_search(head_msg.text, "")
                topic_title = q
        except Exception:
            pass
            
        bt_key = topic_title.lower()
        p_tid = p_topics.get(bt_key)
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
                    p_topics[bt_key] = p_tid
            except Exception as e:
                logger.error(f"Error creando tema '{topic_title}': {e}")
                continue
                
        if not p_tid:
            continue
            
        msg_ids = [m.id for m in t_msgs if not m.action]
        if not msg_ids:
            continue
            
        for i in range(0, len(msg_ids), CHUNK_SIZE):
            chunk = msg_ids[i:i + CHUNK_SIZE]
            for attempt in range(1, 4):
                try:
                    await ensure_clients(cb, cp)
                    
                    # A. Bunker -> DM Prod
                    fwd_res = await cb.forward_messages(
                        entity=prod_user,
                        messages=chunk,
                        from_peer=ent_bunker,
                        drop_author=True
                    )
                    b_fwd = [m.id for m in fwd_res] if isinstance(fwd_res, list) else [fwd_res.id]
                    
                    # B. Prod recibe de DM
                    recv = await cp.get_messages(bunker_user, limit=len(b_fwd))
                    if not isinstance(recv, list):
                        recv = [recv]
                    p_recv = [m.id for m in reversed(recv) if not m.action]
                    
                    # C. Prod reenvía al canal oficial
                    if p_recv:
                        r_ids = [random.randint(1, 2**63 - 1) for _ in p_recv]
                        await cp(ForwardMessagesRequest(
                            from_peer=await cp.get_input_entity(bunker_user),
                            to_peer=ent_prod,
                            id=p_recv,
                            random_id=r_ids,
                            drop_author=True,
                            top_msg_id=p_tid
                        ))
                    
                    # D. Limpieza de DM
                    try:
                        await cb.delete_messages(prod_user, b_fwd, revoke=True)
                        await cp.delete_messages(bunker_user, p_recv, revoke=True)
                    except Exception:
                        pass
                    
                    break
                except errors.FloodWaitError as fe:
                    logger.warning(f"FloodWait de {fe.seconds}s. Esperando...")
                    await asyncio.sleep(fe.seconds + 2)
                except Exception as e:
                    logger.warning(f"Error en reenvío lote ({attempt}/3): {e}")
                    await asyncio.sleep(4.0)
                    await ensure_clients(cb, cp)
                    
            await asyncio.sleep(2.0)
            
        q, y = clean_for_search(topic_title, "")
        extra_note = "Nueva Serie" if is_new else f"+{len(msg_ids)} nuevos episodios"
        series_added.append({"query": q, "year": y, "type": "serie", "note": extra_note})
            
    return series_added

async def send_rich_community_cards(cp, novedades):
    """Envía fichas atractivas con póster oficial, puntuación y sinopsis al tema 22."""
    if not novedades:
        return
        
    logger.info("📢 Publicando fichas de estreno con carátulas en el grupo Comunidad...")
    try:
        ent_comm = await cp.get_input_entity(COMMUNITY_GROUP_ID)
        
        for c_nombre, items in novedades.items():
            for item in items[:6]:  # Máximo 6 fichas destacadas por tanda para no saturar
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
                
                # Si tenemos póster oficial, descargar y enviar con foto
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
                        logger.warning(f"Error enviando imagen de '{title_display}': {pe}")
                        
                # Si no hay imagen, enviar como mensaje con formato enriquecido
                await cp.send_message(
                    entity=ent_comm,
                    message=caption_text,
                    reply_to=COMMUNITY_TOPIC_ID,
                    parse_mode="markdown"
                )
                logger.info(f"  ✅ Mensaje enriquecido enviado para '{title_display}'")
                await asyncio.sleep(2.0)
                
        logger.info("🎉 ¡Todas las fichas con carátula han sido enviadas a la Comunidad!")
    except Exception as e:
        logger.error(f"❌ Error enviando fichas a la Comunidad: {e}")

async def main():
    logger.info("=" * 80)
    logger.info("🚀 ESCÁNER DE NOVEDADES BÚNKER ➔ PRODUCCIÓN + FICHAS CON CARÁTULAS")
    logger.info("=" * 80)
    
    if not SESSION_BUNKER or not SESSION_PROD:
        logger.error("❌ ERROR: SESSION_BUNKER o SESSION_PROD no configuradas.")
        sys.exit(1)
        
    cb = TelegramClient(StringSession(SESSION_BUNKER), API_ID, API_HASH)
    cp = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)
    
    await cb.start()
    await cp.start()
    
    me_p = await cp.get_me()
    me_b = await cb.get_me()
    prod_user = await cb.get_input_entity(me_p.id)
    bunker_user = await cp.get_input_entity(me_b.id)
    
    canales = load_json(MAP_FILE, default=[])
    if not canales:
        logger.error(f"❌ No se encontró o está vacío {MAP_FILE}.")
        sys.exit(1)
        
    novedades_detectadas = {}
    
    for c in canales:
        if not c.get("activo", True) or not c.get("produccion_id"):
            continue
            
        c_nombre = c["nombre"]
        b_id = c["bunker_id"]
        last_id = c.get("ultimo_id_sincronizado", 0)
        is_forum = c.get("is_forum", False)
        
        try:
            ent_bunker = await cb.get_input_entity(b_id)
            latest = await cb.get_messages(ent_bunker, limit=1)
            current_top = latest[0].id if latest else 0
            
            if current_top <= last_id:
                continue
                
            logger.info(f"🔔 Detectada actividad en '{c_nombre}' (IDs {last_id} ➔ {current_top})")
            
            new_msgs = [m async for m in cb.iter_messages(ent_bunker, min_id=last_id, reverse=True) 
                        if not m.action and (m.media or m.text)]
            if not new_msgs:
                c["ultimo_id_sincronizado"] = current_top
                continue
                
            ent_prod = await cp.get_input_entity(c["produccion_id"])
            if not is_forum:
                items = await sync_channel_peliculas(cb, cp, c, prod_user, bunker_user, ent_bunker, ent_prod, new_msgs)
            else:
                items = await sync_channel_series(cb, cp, c, prod_user, bunker_user, ent_bunker, ent_prod, new_msgs)
                
            c["ultimo_id_sincronizado"] = current_top
            if items:
                novedades_detectadas[c_nombre] = items
                logger.info(f"✅ {len(items)} títulos procesados en '{c_nombre}'.")
                
        except Exception as e:
            logger.error(f"Error procesando canal '{c_nombre}': {e}")
            
    save_json(MAP_FILE, canales)
    
    if novedades_detectadas:
        logger.info("\n🎉 Novedades detectadas en esta revisión. Enviando fichas con carátula...")
        await send_rich_community_cards(cp, novedades_detectadas)
    else:
        logger.info("\n☕ Sin novedades en ningún búnker. Todo el catálogo se encuentra al día.")
        
    await cb.disconnect()
    await cp.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
