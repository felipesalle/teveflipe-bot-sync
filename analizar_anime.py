import asyncio
import json
import logging
import os
import re
from collections import defaultdict
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import (
    MessageMediaDocument,
    DocumentAttributeVideo,
    DocumentAttributeFilename
)
from telethon.tl.functions.messages import GetForumTopicsRequest

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("analizar_anime")

API_ID = int(os.getenv("TELEGRAM_API_ID") or 28045969)
API_HASH = os.getenv("TELEGRAM_API_HASH") or "d8e515c5687943e5e0bf046f87c3d2cc"
STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION") or ""

TARGET_CHAT_ID = int(os.getenv("TARGET_CHAT_ID") or "-1002257262928")
TARGET_TOPIC_ID = int(os.getenv("TARGET_TOPIC_ID") or "316312")

VIDEO_EXTENSIONS = (".mkv", ".mp4", ".avi", ".mov", ".webm", ".ts", ".m4v")

def is_video_message(message) -> bool:
    if not message.media:
        return False
    if getattr(message, "video", None):
        return True
    if isinstance(message.media, MessageMediaDocument):
        doc = message.media.document
        if doc:
            if doc.mime_type and doc.mime_type.startswith("video/"):
                return True
            for attr in doc.attributes:
                if isinstance(attr, DocumentAttributeVideo):
                    return True
                if isinstance(attr, DocumentAttributeFilename):
                    if attr.file_name and attr.file_name.lower().endswith(VIDEO_EXTENSIONS):
                        return True
    return False

def extract_file_name(message) -> str:
    if message.media and isinstance(message.media, MessageMediaDocument) and message.media.document:
        for attr in message.media.document.attributes:
            if isinstance(attr, DocumentAttributeFilename):
                return attr.file_name or ""
    return ""

def get_media_size(message) -> int:
    if getattr(message, "file", None) and hasattr(message.file, "size"):
        return message.file.size or 0
    if message.media and isinstance(message.media, MessageMediaDocument) and message.media.document:
        return getattr(message.media.document, "size", 0) or 0
    return 0

def get_video_duration(message) -> int:
    if getattr(message, "video", None) and hasattr(message.video, "duration"):
        return message.video.duration or 0
    if message.media and isinstance(message.media, MessageMediaDocument) and message.media.document:
        for attr in message.media.document.attributes:
            if isinstance(attr, DocumentAttributeVideo):
                return getattr(attr, "duration", 0) or 0
    return 0

def clean_anime_title(filename: str, caption: str = "") -> dict:
    raw = filename
    if not raw and caption:
        raw = caption.strip().split("\n")[0]
    
    base = re.sub(r"\.(mkv|mp4|avi|mov|webm|ts|m4v)$", "", raw, flags=re.IGNORECASE).strip()
    
    is_movie = bool(re.search(r"(?i)\b(pel[ií]cula|movie|film|gekijouban)\b", base))
    is_ova = bool(re.search(r"(?i)\b(ova|oad|especial|special)\b", base))

    season = 1
    episode = None

    tags_removed = re.sub(r"\[[^\]]*\]|\([^\)]*\)", " ", base).strip()

    m_se = re.search(r"(?i)\b(?:S|T)(\d{1,2})\s*[-_xX]?\s*(?:E|EP|Cap[ií]tulo)?\s*(\d{1,3})\b", tags_removed)
    if not m_se:
        m_se = re.search(r"\b(\d{1,2})[xX](\d{1,3})\b", tags_removed)

    if m_se:
        season = int(m_se.group(1))
        episode = int(m_se.group(2))
        title_part = tags_removed[:m_se.start()].strip()
    else:
        m_cap = re.search(r"(?i)\b(?:cap[ií]tulo|cap|episodio|ep)\s*(\d{1,4})\b", tags_removed)
        if m_cap:
            episode = int(m_cap.group(1))
            title_part = tags_removed[:m_cap.start()].strip()
            m_t = re.search(r"(?i)\b(?:temporada|temp|season|t)\s*(\d{1,2})\b", title_part)
            if m_t:
                season = int(m_t.group(1))
                title_part = title_part[:m_t.start()].strip()
        else:
            m_dash = re.search(r"\s*-\s*(\d{1,4})\s*(?:-.*)?$", tags_removed)
            if m_dash:
                episode = int(m_dash.group(1))
                title_part = tags_removed[:m_dash.start()].strip()
            else:
                m_end = re.search(r"(.*?)\s+(\d{1,3})$", tags_removed)
                if m_end and not is_movie:
                    episode = int(m_end.group(2))
                    title_part = m_end.group(1).strip()
                else:
                    title_part = tags_removed

    title_part = re.sub(r"^\d{1,3}\s*[-_.]?\s*", "", title_part).strip()
    title_part = re.sub(r"[-_.]+", " ", title_part).strip()
    title_part = re.sub(r"\s{2,}", " ", title_part)

    if not title_part or len(title_part) < 2:
        title_part = base

    title_clean = title_part.strip().title()

    return {
        "title": title_clean,
        "season": season,
        "episode": episode,
        "is_movie": is_movie,
        "is_ova": is_ova,
        "raw_filename": raw
    }

async def analyze():
    if not STRING_SESSION:
        logger.error("TELEGRAM_STRING_SESSION no configurada.")
        return

    async with TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH) as client:
        logger.info(f"Buscando el chat objetivo: {TARGET_CHAT_ID}...")
        entity = None
        async for dialog in client.iter_dialogs(limit=200):
            if dialog.id == TARGET_CHAT_ID or str(TARGET_CHAT_ID).replace("-100", "") in str(dialog.id):
                entity = dialog.entity
                logger.info(f"¡Chat encontrado en diálogos!: {dialog.title} (ID {dialog.id})")
                break

        if not entity:
            try:
                entity = await client.get_entity(TARGET_CHAT_ID)
                logger.info(f"Entidad obtenida directamente: {getattr(entity, 'title', 'Sin título')} (ID {entity.id})")
            except Exception as e:
                logger.error(f"No se pudo resolver la entidad {TARGET_CHAT_ID}: {e}")
                return

        chat_title = getattr(entity, "title", "Canal / Grupo")
        is_forum = getattr(entity, "forum", False)
        logger.info(f"=== CHAT: '{chat_title}' | ID: {entity.id} | Es Foro: {is_forum} ===")

        all_topics = []
        target_topic_title = f"Topic {TARGET_TOPIC_ID}"

        if is_forum:
            try:
                offset_id = 0
                offset_date = None
                offset_topic = 0
                while True:
                    res = await client(GetForumTopicsRequest(
                        peer=entity,
                        offset_date=offset_date,
                        offset_id=offset_id,
                        offset_topic=offset_topic,
                        limit=100
                    ))
                    if not res.topics:
                        break
                    for t in res.topics:
                        all_topics.append({
                            "id": t.id,
                            "title": t.title,
                            "top_message": t.top_message,
                            "total_messages": getattr(t, "total_messages", 0)
                        })
                        if t.id == TARGET_TOPIC_ID:
                            target_topic_title = t.title
                    if len(res.topics) < 100:
                        break
                    last = res.topics[-1]
                    offset_id = last.top_message
                    offset_topic = last.id
            except Exception as e:
                logger.warning(f"Error listando temas del foro: {e}")

        logger.info(f"Total de temas en el foro: {len(all_topics)}")
        for t in all_topics:
            logger.info(f"  Tema: ID {t['id']} -> '{t['title']}'")

        logger.info(f"Iniciando escaneo del Tema objetivo ID {TARGET_TOPIC_ID} ('{target_topic_title}')...")

        videos_found = []
        text_fiches = []
        total_msg_scanned = 0

        iter_kwargs = {"limit": None, "reverse": True}
        if is_forum and TARGET_TOPIC_ID != 0:
            iter_kwargs["reply_to"] = TARGET_TOPIC_ID

        async for msg in client.iter_messages(entity, **iter_kwargs):
            total_msg_scanned += 1
            if total_msg_scanned % 500 == 0:
                logger.info(f"Procesados {total_msg_scanned} mensajes... ({len(videos_found)} videos encontrados)")

            if is_video_message(msg):
                fn = extract_file_name(msg)
                caption = msg.text or ""
                size = get_media_size(msg)
                duration = get_video_duration(msg)
                parsed = clean_anime_title(fn, caption)

                videos_found.append({
                    "message_id": msg.id,
                    "date": msg.date.isoformat() if msg.date else "",
                    "file_name": fn,
                    "caption": caption[:150],
                    "size_bytes": size,
                    "size_mb": round(size / (1024 * 1024), 2),
                    "duration_sec": duration,
                    "duration_min": round(duration / 60, 1),
                    "parsed": parsed
                })
            elif (msg.text and len(msg.text.strip()) > 30) or msg.photo:
                text = (msg.text or "").strip()
                if any(kw in text.lower() for kw in ["sinopsis", "género", "anime", "episodios", "temporada", "filmaffinity"]):
                    text_fiches.append({
                        "message_id": msg.id,
                        "text": text[:300]
                    })

        logger.info(f"Escaneo finalizado. Total mensajes: {total_msg_scanned}, Total videos: {len(videos_found)}")

        series_groups = defaultdict(list)
        pelicula_candidates = []

        for v in videos_found:
            p = v["parsed"]
            dur = v["duration_sec"]

            if p["is_movie"] or (dur >= 3000 and p["episode"] is None):
                pelicula_candidates.append(v)
            else:
                series_groups[p["title"]].append(v)

        series_final = {}
        for title, vids in series_groups.items():
            if len(vids) == 1:
                v0 = vids[0]
                p0 = v0["parsed"]
                dur0 = v0["duration_sec"]
                if dur0 >= 3000 or p0["episode"] is None or p0["is_movie"]:
                    pelicula_candidates.append(v0)
                    continue
            
            vids_sorted = sorted(vids, key=lambda x: (x["parsed"]["season"] or 1, x["parsed"]["episode"] or 0, x["message_id"]))
            episodes = [x["parsed"]["episode"] for x in vids_sorted if x["parsed"]["episode"] is not None]
            seasons = sorted(list(set(x["parsed"]["season"] for x in vids_sorted if x["parsed"]["season"] is not None)))
            total_size_mb = sum(x["size_mb"] for x in vids_sorted)

            series_final[title] = {
                "title": title,
                "total_episodes": len(vids_sorted),
                "seasons": seasons,
                "episodes_detected": episodes,
                "total_size_gb": round(total_size_mb / 1024, 2),
                "avg_duration_min": round(sum(x["duration_min"] for x in vids_sorted) / len(vids_sorted), 1) if vids_sorted else 0,
                "msg_range": f"{vids_sorted[0]['message_id']} - {vids_sorted[-1]['message_id']}",
                "sample_files": [x["file_name"] for x in vids_sorted[:3]]
            }

        peliculas_sorted = sorted(pelicula_candidates, key=lambda x: x["parsed"]["title"])
        peliculas_final = []
        for p in peliculas_sorted:
            peliculas_final.append({
                "title": p["parsed"]["title"],
                "file_name": p["file_name"],
                "duration_min": p["duration_min"],
                "size_mb": p["size_mb"],
                "message_id": p["message_id"]
            })

        total_series_count = len(series_final)
        total_episodes_count = sum(s["total_episodes"] for s in series_final.values())
        total_peliculas_count = len(peliculas_final)
        total_videos = len(videos_found)
        total_gb = round(sum(v["size_mb"] for v in videos_found) / 1024, 2)

        summary = {
            "chat_title": chat_title,
            "chat_id": entity.id,
            "topic_id": TARGET_TOPIC_ID,
            "topic_title": target_topic_title,
            "is_forum": is_forum,
            "total_forum_topics": len(all_topics),
            "all_topics": all_topics,
            "total_messages_scanned": total_msg_scanned,
            "total_videos_found": total_videos,
            "total_series_count": total_series_count,
            "total_episodes_in_series": total_episodes_count,
            "total_peliculas_count": total_peliculas_count,
            "total_size_gb": total_gb,
            "series": series_final,
            "peliculas": peliculas_final
        }

        with open("analisis_anime.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        logger.info("Archivo 'analisis_anime.json' generado con éxito.")

        md = []
        md.append(f"# ⛩️ Informe de Auditoría y Catálogo Anime")
        md.append(f"\n**Canal/Grupo:** {chat_title} (`{entity.id}`)")
        md.append(f"**Tema Analizado:** {target_topic_title} (ID `{TARGET_TOPIC_ID}`)")
        md.append(f"**Tipo de Chat:** {'Grupo con Foros/Temas' if is_forum else 'Canal / Grupo Estándar'}")
        md.append(f"\n---")
        md.append(f"\n## 📊 Resumen Ejecutivo del Contenido")
        md.append(f"| Métrica | Cantidad |")
        md.append(f"| :--- | :---: |")
        md.append(f"| **Total de Vídeos Encontrados** | **{total_videos}** |")
        md.append(f"| **Series Anime Distintas** | **{total_series_count}** |")
        md.append(f"| **Total Episodios de Series** | **{total_episodes_count}** |")
        md.append(f"| **Películas Anime Detectadas** | **{total_peliculas_count}** |")
        md.append(f"| **Espacio Total en Disco** | **{total_gb} GB** |")
        md.append(f"\n---")

        if is_forum and all_topics:
            md.append(f"\n## 📑 Estructura de Temas del Grupo Fuente")
            md.append(f"| ID Tema | Título del Tema | Mensajes Aprox |")
            md.append(f"| :---: | :--- | :---: |")
            for t in all_topics:
                highlight = " ⭐ (Objetivo)" if t["id"] == TARGET_TOPIC_ID else ""
                md.append(f"| `{t['id']}` | **{t['title']}**{highlight} | {t.get('total_messages', '-')} |")
            md.append(f"\n---")

        md.append(f"\n## 📺 Catálogo Detallado de Series Anime ({total_series_count} series)")
        md.append(f"| # | Título de la Serie | Temporadas | Episodios | Tamaño | Duración Media | Rango Mensajes |")
        md.append(f"|---|-------------------|:----------:|:---------:|:------:|:--------------:|:--------------:|")
        
        idx = 1
        for title, s in sorted(series_final.items(), key=lambda x: x[0]):
            seasons_str = f"T{', T'.join(map(str, s['seasons']))}" if s['seasons'] else "T1"
            md.append(f"| {idx} | **{s['title']}** | {seasons_str} | {s['total_episodes']} caps | {s['total_size_gb']} GB | {s['avg_duration_min']} min | `{s['msg_range']}` |")
            idx += 1

        md.append(f"\n---")
        md.append(f"\n## 🎬 Catálogo Detallado de Películas Anime ({total_peliculas_count} películas)")
        md.append(f"| # | Título de la Película | Duración | Tamaño | Archivo | ID Msg |")
        md.append(f"|---|-----------------------|:--------:|:------:|:--------|:------:|")
        
        idx_p = 1
        for p in peliculas_final:
            md.append(f"| {idx_p} | **{p['title']}** | {p['duration_min']} min | {p['size_mb']} MB | `{p['file_name']}` | `{p['message_id']}` |")
            idx_p += 1

        md.append(f"\n---")
        md.append(f"\n## 💡 Recomendaciones para Crear tus Canales en TeveFlipe")
        md.append(f"1. **Canal 1: Películas Anime** (Canal estándar de difusión):")
        md.append(f"   - Alojar las **{total_peliculas_count} películas** identificadas.")
        md.append(f"   - Cada película es un post con su video y carátula. TeveFlipe las clasificará automáticamente bajo la categoría *'Películas Anime'* en la app de TV.")
        md.append(f"2. **Canal 2: Series Anime** (Grupo con Foros/Temas habilitados):")
        md.append(f"   - Activar el modo Foro en el grupo destino.")
        md.append(f"   - Crear **un Tema por cada Serie Anime** (ej. Tema *'Death Note'*, Tema *'Attack on Titan'*, etc.).")
        md.append(f"   - TeveFlipe TV indexará cada tema como una serie completa con su lista de capítulos ordenados automáticamente.")

        with open("INFORME_ANIME.md", "w", encoding="utf-8") as f:
            f.write("\n".join(md))
        logger.info("Archivo 'INFORME_ANIME.md' generado con éxito.")

if __name__ == "__main__":
    asyncio.run(analyze())
