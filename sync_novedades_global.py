import asyncio
import json
import logging
import os
import random
import re
import sys
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

def clean_title(text: str, filename: str) -> str:
    raw = ""
    if filename:
        raw = os.path.splitext(filename)[0]
    elif text:
        first_line = text.strip().split("\n")[0]
        raw = first_line[:80]
    else:
        return "Nuevo Contenido"
    
    clean = re.sub(r'\[.*?\]|\(.*?\)', '', raw).strip()
    return clean[:60] if clean else raw[:60]

async def sync_channel_peliculas(cb, cp, c, prod_user, bunker_user, ent_bunker, ent_prod, new_msgs):
    """Reenvía nuevas películas."""
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
        t_clean = clean_title(m.text or "", fname)
        if t_clean and t_clean not in titles_added:
            titles_added.append(t_clean)
            
    return titles_added

async def sync_channel_series(cb, cp, c, prod_user, bunker_user, ent_bunker, ent_prod, new_msgs):
    """Reenvía nuevos episodios / series a sus respectivos temas."""
    # Agrupar mensajes por topic_id
    msgs_by_topic = {}
    for m in new_msgs:
        top_id = None
        if m.reply_to:
            top_id = getattr(m.reply_to, 'reply_to_top_id', None) or getattr(m.reply_to, 'reply_to_msg_id', None)
        if not top_id:
            top_id = m.id  # Puede ser el mensaje de creación del tema
        msgs_by_topic.setdefault(top_id, []).append(m)
        
    # Obtener temas de Producción
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
        # Obtener título del tema en Búnker
        topic_title = f"Tema {b_tid}"
        try:
            head_msg = await cb.get_messages(ent_bunker, ids=b_tid)
            if head_msg and hasattr(head_msg, 'action') and hasattr(head_msg.action, 'title'):
                topic_title = head_msg.action.title.strip()
            elif head_msg and head_msg.file and head_msg.file.name:
                topic_title = clean_title("", head_msg.file.name)
            elif head_msg and head_msg.text:
                topic_title = clean_title(head_msg.text, "")
        except Exception:
            pass
            
        bt_key = topic_title.lower()
        p_tid = p_topics.get(bt_key)
        is_new = False
        
        if not p_tid:
            # Crear tema nuevo en Producción
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
            
        # Replicar mensajes a p_tid
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
            
        if is_new:
            series_added.append(f"{topic_title} (Nueva Serie)")
        else:
            series_added.append(f"{topic_title} (+{len(msg_ids)} nuevos eps)")
            
    return series_added

async def send_community_announcement(cp, novedades):
    if not novedades:
        return
        
    logger.info("📢 Publicando aviso de estrenos en el grupo Comunidad...")
    try:
        ent_comm = await cp.get_input_entity(COMMUNITY_GROUP_ID)
        
        lines = [
            "✨ **¡ESTRENOS Y NUEVOS CONTENIDOS EN TEVEFLIPE!** ✨",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "Se acaban de agregar nuevos títulos a los canales oficiales:\n"
        ]
        
        for cat_name, items in novedades.items():
            lines.append(f"📌 **{cat_name}:**")
            for it in items[:10]:
                lines.append(f"  • {it}")
            if len(items) > 10:
                lines.append(f"  • ... y {len(items)-10} más.")
            lines.append("")
            
        lines.append("🍿 _¡Ya disponible para ver y disfrutar en TeVeFLIPE!_")
        message_text = "\n".join(lines)
        
        await cp.send_message(
            entity=ent_comm,
            message=message_text,
            reply_to=COMMUNITY_TOPIC_ID,
            parse_mode="markdown"
        )
        logger.info("✅ ¡Aviso de estrenos enviado con éxito al tema 22 de la Comunidad!")
    except Exception as e:
        logger.error(f"❌ Error enviando aviso a la Comunidad: {e}")

async def main():
    logger.info("=" * 80)
    logger.info("🚀 ESCÁNER DE NOVEDADES BÚNKER ➔ PRODUCCIÓN + AVISO COMUNIDAD")
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
                # Canal al día, comprobación instantánea (0.1s)
                continue
                
            logger.info(f"🔔 Detectada actividad en '{c_nombre}' (IDs {last_id} ➔ {current_top})")
            
            # Obtener solo mensajes nuevos
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
            
    # Guardar estado actualizado en canales_map.json
    save_json(MAP_FILE, canales)
    
    # Publicar anuncio en Comunidad si hubo novedades
    if novedades_detectadas:
        logger.info("\n🎉 Novedades detectadas en esta revisión. Enviando aviso...")
        await send_community_announcement(cp, novedades_detectadas)
    else:
        logger.info("\n☕ Sin novedades en ningún búnker. Todo el catálogo se encuentra al día.")
        
    await cb.disconnect()
    await cp.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
