import os
import sys
import json
import asyncio
import logging
import random
import re
import requests
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ForwardMessagesRequest, CreateForumTopicRequest, GetForumTopicsRequest

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("SyncSolicitado")

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_BUNKER = os.getenv("SESSION_BUNKER") or ""
SESSION_PROD = os.getenv("SESSION_PROD") or ""
COMMUNITY_GROUP_ID = int(os.getenv("COMMUNITY_GROUP_ID", "-1003990716596"))
COMMUNITY_TOPIC_ID = int(os.getenv("COMMUNITY_TOPIC_ID", "22"))
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "2b7cd7b237fe99884613b230a910a09c")
MAP_FILE = "canales_map.json"
CHUNK_SIZE = 5

VIDEO_EXTS = ('.mp4', '.mkv', '.avi', '.mov', '.ts', '.m4v', '.wmv', '.flv', '.webm', '.rar', '.7z')

def is_user_excluded(title: str, fname: str) -> bool:
    t = f"{title} {fname}".lower()
    if "isla de las tentaciones" in t or "tentaciones" in t:
        return True
    if "la voz" in t or "la_voz" in t:
        return True
    return False

def clean_title_for_search(text: str, filename: str) -> str:
    candidate = filename or text
    if not candidate:
        return ""
    # Remover extensiones
    candidate = re.sub(r'\.(mkv|mp4|avi|rar|7z|\d{3})$', '', candidate, flags=re.IGNORECASE)
    candidate = re.sub(r'[\._\-]', ' ', candidate)
    # Remover etiquetas comunes
    candidate = re.sub(r'(1080p|720p|4k|uhd|web-dl|webdl|bluray|bdrip|castellano|latino|spanish|x264|x265|hevc|h264|amzn|dsnp|mvplus|ac3|eac3|dts|by.*)', '', candidate, flags=re.IGNORECASE)
    return candidate.strip()

async def get_tmdb_card(query: str, is_series: bool = False):
    try:
        url = "https://api.themoviedb.org/3/search/tv" if is_series else "https://api.themoviedb.org/3/search/movie"
        resp = requests.get(url, params={"api_key": TMDB_API_KEY, "query": query, "language": "es-ES"}, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results", [])
            if results:
                first = results[0]
                title = first.get("name" if is_series else "title")
                overview = first.get("overview", "")
                poster_path = first.get("poster_path")
                vote = first.get("vote_average", 0)
                year = (first.get("first_air_date" if is_series else "release_date") or "")[:4]
                poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
                return {
                    "title": title,
                    "overview": overview[:300] + "..." if len(overview) > 300 else overview,
                    "year": year,
                    "rating": vote,
                    "poster_url": poster_url
                }
    except Exception as e:
        logger.warning(f"Error consultando TMDB para '{query}': {e}")
    return None

async def send_community_announcement(client, title: str, category: str, is_series: bool = False):
    try:
        info = await get_tmdb_card(title, is_series=is_series)
        caption_lines = [
            f"🎬 **¡Novedad Disponible en TeVeFLIPE!**" if not is_series else f"📺 **¡Nueva Serie en TeVeFLIPE!**",
            "",
            f"📌 **Título:** {info['title'] if info else title}",
            f"📁 **Categoría:** {category.capitalize()}"
        ]
        if info and info.get("year"):
            caption_lines.append(f"📅 **Año:** {info['year']}")
        if info and info.get("rating"):
            caption_lines.append(f"⭐ **Valoración:** {info['rating']:.1f}/10")
        if info and info.get("overview"):
            caption_lines.append(f"\n📖 **Sinopsis:**\n{info['overview']}")
        
        caption_lines.append("\n🍿 _¡Disponible ahora en tus canales y en la app!_")
        caption = "\n".join(caption_lines)

        if info and info.get("poster_url"):
            try:
                img_data = requests.get(info["poster_url"], timeout=5).content
                import io
                file_obj = io.BytesIO(img_data)
                file_obj.name = "poster.jpg"
                await client.send_file(
                    COMMUNITY_GROUP_ID,
                    file_obj,
                    caption=caption,
                    reply_to=COMMUNITY_TOPIC_ID
                )
                logger.info(f"📢 Ficha publicada con carátula en Comunidad: {title}")
                return
            except Exception as e_img:
                logger.warning(f"Error subiendo poster: {e_img}")

        await client.send_message(
            COMMUNITY_GROUP_ID,
            caption,
            reply_to=COMMUNITY_TOPIC_ID
        )
        logger.info(f"📢 Ficha publicada en texto en Comunidad: {title}")
    except Exception as e:
        logger.warning(f"No se pudo enviar anuncio a Comunidad para '{title}': {e}")

async def sync_channel(client, c):
    c_nombre = c["nombre"]
    b_id = c["bunker_id"]
    p_id = c["produccion_id"]
    last_id = c.get("ultimo_id_sincronizado", 0)
    topic_id = c.get("topic_id")
    is_forum = c.get("is_forum", False)
    categoria = c.get("categoria", "general")

    logger.info(f"\n==================================================")
    logger.info(f"🚀 Procesando canal: {c_nombre}")
    logger.info(f"   Puntero inicial: {last_id}")
    logger.info(f"==================================================")

    ent_bunker = await client.get_input_entity(b_id)
    ent_prod = await client.get_input_entity(p_id)

    # 1. Obtener mensajes existentes en Producción para no duplicar
    existing_filenames = set()
    try:
        if not is_forum:
            async for pm in client.iter_messages(ent_prod, limit=1000):
                if pm.file and hasattr(pm.file, 'name') and pm.file.name:
                    existing_filenames.add(pm.file.name.lower().strip())
    except Exception as e:
        logger.warning(f"Aviso leyendo historial de producción: {e}")

    # 2. Leer mensajes nuevos del búnker
    iter_kwargs = {"min_id": last_id, "reverse": True}
    if topic_id:
        iter_kwargs["reply_to"] = topic_id

    bunker_msgs = [m async for m in client.iter_messages(ent_bunker, **iter_kwargs)
                   if not m.action and (m.media or m.text)]

    if not bunker_msgs:
        logger.info(f"☕ Sin mensajes nuevos en {c_nombre}.")
        return

    logger.info(f"📥 Encontrados {len(bunker_msgs)} mensajes en Búnker.")

    if not is_forum:
        # Modo Canal Plano (Películas, Infantiles, Anime, Conciertos, Documentales)
        valid_chunks = []
        current_chunk = []
        titles_forwarded = []
        highest_id = last_id

        for m in bunker_msgs:
            highest_id = max(highest_id, m.id)
            fn = (m.file.name if m.file and hasattr(m.file, 'name') else "") or ""
            txt = (m.message or "").strip()
            
            # FILTRO EXCLUSIONES DE USUARIO
            if is_user_excluded(txt, fn):
                logger.info(f"🚫 [Exclusión solicitada por usuario] Omitiendo: {fn or txt[:50]}")
                continue

            # FILTRO DUPLICADOS EN PRODUCCIÓN
            if fn and fn.lower().strip() in existing_filenames:
                logger.info(f"⏩ [Anti-duplicado] Ya existe en Producción: {fn}")
                continue

            current_chunk.append(m.id)
            clean_t = clean_title_for_search(txt, fn)
            if clean_t and clean_t not in titles_forwarded:
                titles_forwarded.append(clean_t)

            if len(current_chunk) >= CHUNK_SIZE:
                valid_chunks.append(current_chunk)
                current_chunk = []

        if current_chunk:
            valid_chunks.append(current_chunk)

        # Enviar chunks
        total_reenviados = 0
        for chunk in valid_chunks:
            for attempt in range(1, 4):
                try:
                    await client(ForwardMessagesRequest(
                        from_peer=ent_bunker,
                        to_peer=ent_prod,
                        id=chunk,
                        random_id=[random.randint(1, 2**63 - 1) for _ in chunk],
                        drop_author=True
                    ))
                    total_reenviados += len(chunk)
                    logger.info(f"✅ Reenviado lote de {len(chunk)} mensajes en {c_nombre}.")
                    await asyncio.sleep(2.0)
                    break
                except errors.FloodWaitError as fwe:
                    logger.warning(f"FloodWait {fwe.seconds}s. Esperando...")
                    await asyncio.sleep(fwe.seconds + 2)
                except Exception as e:
                    logger.error(f"Error reenviando lote ({attempt}/3): {e}")
                    await asyncio.sleep(3.0)

        # Publicar anuncios en Comunidad
        for t in titles_forwarded[:4]:
            await send_community_announcement(client, t, categoria, is_series=False)

        c["ultimo_id_sincronizado"] = highest_id
        logger.info(f"🏁 Finalizado {c_nombre}. Puntero actualizado a {highest_id}. Mensajes reenviados: {total_reenviados}")

    else:
        # Modo Foro (Series Turcas / Çalıkuşu)
        highest_id = last_id
        # Agrupar mensajes en serie
        series_topic_name = "Çalıkuşu"
        
        # 1. Buscar o crear tema en Producción
        target_tid = None
        try:
            topics_req = await client(GetForumTopicsRequest(channel=ent_prod, offset_date=0, offset_id=0, offset_topic=0, limit=100))
            for t in topics_req.topics:
                if series_topic_name.lower() in t.title.lower():
                    target_tid = t.id
                    logger.info(f"📌 Tema existente encontrado en Producción: '{t.title}' (ID: {target_tid})")
                    break
        except Exception as e_t:
            logger.warning(f"Aviso consultando temas: {e_t}")

        if not target_tid:
            logger.info(f"✨ Creando nuevo tema en Producción: '{series_topic_name}'...")
            try:
                new_top = await client(CreateForumTopicRequest(
                    channel=ent_prod,
                    title=series_topic_name,
                    icon_color=0x6FB9F0
                ))
                for upd in getattr(new_top, 'updates', []):
                    if hasattr(upd, 'message') and hasattr(upd.message, 'id'):
                        target_tid = upd.message.id
                        break
                    elif hasattr(upd, 'id'):
                        target_tid = upd.id
                        break
                logger.info(f"✅ Tema creado con éxito: ID {target_tid}")
            except Exception as ce:
                logger.error(f"❌ Error creando tema: {ce}")
                return

        # 2. Consultar archivos ya existentes dentro del tema
        existing_in_topic = set()
        if target_tid:
            try:
                async for tm in client.iter_messages(ent_prod, reply_to=target_tid, limit=200):
                    if tm.file and hasattr(tm.file, 'name') and tm.file.name:
                        existing_in_topic.add(tm.file.name.lower().strip())
            except Exception as e_top_scan:
                logger.warning(f"Aviso escaneando tema: {e_top_scan}")

        # 3. Filtrar episodios
        episodes_to_forward = []
        for m in bunker_msgs:
            highest_id = max(highest_id, m.id)
            fn = (m.file.name if m.file and hasattr(m.file, 'name') else "") or ""
            txt = (m.message or "").strip()
            
            if is_user_excluded(txt, fn):
                continue

            if fn and fn.lower().strip() in existing_in_topic:
                logger.info(f"⏩ [Anti-duplicado] Capítulo ya existe en tema: {fn}")
                continue

            episodes_to_forward.append(m.id)

        # 4. Reenviar en lotes con top_msg_id
        total_ep_reenviados = 0
        for i in range(0, len(episodes_to_forward), CHUNK_SIZE):
            chunk = episodes_to_forward[i:i + CHUNK_SIZE]
            for attempt in range(1, 4):
                try:
                    await client(ForwardMessagesRequest(
                        from_peer=ent_bunker,
                        to_peer=ent_prod,
                        id=chunk,
                        random_id=[random.randint(1, 2**63 - 1) for _ in chunk],
                        drop_author=True,
                        top_msg_id=target_tid
                    ))
                    total_ep_reenviados += len(chunk)
                    logger.info(f"✅ Reenviados {len(chunk)} capítulos al tema '{series_topic_name}'.")
                    await asyncio.sleep(2.0)
                    break
                except errors.FloodWaitError as fwe:
                    logger.warning(f"FloodWait {fwe.seconds}s. Esperando...")
                    await asyncio.sleep(fwe.seconds + 2)
                except Exception as e:
                    logger.error(f"Error reenviando episodios ({attempt}/3): {e}")
                    await asyncio.sleep(3.0)

        # Anuncio en comunidad
        await send_community_announcement(client, series_topic_name, categoria, is_series=True)
        c["ultimo_id_sincronizado"] = highest_id
        logger.info(f"🏁 Finalizado {c_nombre}. Puntero actualizado a {highest_id}. Capítulos reenviados: {total_ep_reenviados}")

async def main():
    print("=" * 70)
    print("🚀 EJECUTANDO SINCRONIZACIÓN SOLICITADA")
    print("   (Exclusiones aplicadas: La Isla de las Tentaciones, La Voz)")
    print("=" * 70)

    client = TelegramClient(StringSession(SESSION_BUNKER), API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    logger.info(f"Conectado como: {me.first_name} ({me.id})")
    
    await client.get_dialogs(limit=None)

    with open(MAP_FILE, "r", encoding="utf-8") as f:
        canales = json.load(f)

    # Canales a sincronizar solicitados por el usuario
    target_ids = ['peliculas_infantiles', 'peliculas_anime', 'conciertos', 'documentales', 'series_turcas']

    for cid in target_ids:
        c = next((x for x in canales if x['id'] == cid), None)
        if not c:
            continue
        try:
            await sync_channel(client, c)
        except Exception as e:
            logger.error(f"❌ Error en canal {cid}: {e}")

    # Guardar estado actualizado
    with open(MAP_FILE, "w", encoding="utf-8") as f:
        json.dump(canales, f, indent=2, ensure_ascii=False)
    logger.info("💾 Guardado canales_map.json con nuevos punteros.")

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
