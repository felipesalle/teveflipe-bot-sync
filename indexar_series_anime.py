import asyncio
import json
import logging
import os
import re
import sys
from collections import defaultdict
from telethon import TelegramClient, errors, utils
from telethon.sessions import StringSession
from telethon.tl.types import (
    MessageMediaDocument,
    DocumentAttributeVideo,
    DocumentAttributeFilename
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("IndexarAnime")

API_ID = int(os.environ.get("TELEGRAM_API_ID", 28045969))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION = os.environ.get("TELEGRAM_STRING_SESSION", "")

CONFIG_FILE = "anime_config.json"
INDEX_FILE = "index_series_anime.json"
REPORT_FILE = "REPORTE_SERIES_ANIME_VERIFICADAS.md"

VIDEO_EXTENSIONS = (".mkv", ".mp4", ".avi", ".mov", ".webm", ".ts", ".m4v")

def is_video_message(message) -> bool:
    if not message or not message.media:
        return False
    if getattr(message, "video", None):
        return True
    if getattr(message, "file", None):
        mime = (getattr(message.file, "mime_type", "") or "").lower()
        if mime.startswith("video/"):
            return True
        name = (getattr(message.file, "name", "") or "").lower()
        if name.endswith(VIDEO_EXTENSIONS):
            return True
    if isinstance(message.media, MessageMediaDocument) and message.media.document:
        doc = message.media.document
        mime = (doc.mime_type or "").lower()
        if mime.startswith("video/"):
            return True
        for attr in doc.attributes:
            if isinstance(attr, DocumentAttributeVideo):
                return True
            if isinstance(attr, DocumentAttributeFilename):
                fname = (attr.file_name or "").lower()
                if fname.endswith(VIDEO_EXTENSIONS):
                    return True
    return False

def extract_file_name(message) -> str:
    if getattr(message, "file", None) and getattr(message.file, "name", None):
        return message.file.name or ""
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

def parse_anime_info(fn: str, caption: str = "") -> tuple[str, int, int, bool]:
    """
    Parsea de forma ultra-precisa el título de la serie, temporada y capítulo.
    Retorna: (titulo_serie, temporada, capitulo, es_pelicula)
    """
    raw = fn or (caption.split("\n")[0] if caption else "")
    base = re.sub(r"\.(mkv|mp4|avi|mov|webm|ts|m4v)$", "", raw, flags=re.IGNORECASE).strip()

    is_movie = bool(re.search(r"(?i)\b(pel[ií]cula|movie|film|gekijouban)\b", base))

    # Limpiar corchetes de fansub / resoluciones / canales telegram
    t = re.sub(r"\[[^\]]*\]", " ", base)
    t = re.sub(r"@[\w_]+", " ", t)
    t = re.sub(r"(?i)\b(1080p|720p|480p|4k|2160p|bluray|bdrip|web-?dl|webrip|dvdrip|hdtv|x264|x265|hevc|aac|dual|latino|castellano|spanish|vose|microhd)\b", " ", t)

    season = 1
    episode = None
    title = ""

    # Caso 1: S01E02 o 1x02
    m_se = re.search(r"(?i)\b(?:s(\d{1,2})[-_.]?e(\d{1,3})|(\d{1,2})x(\d{1,3}))\b", t)
    if m_se:
        if m_se.group(1):
            season = int(m_se.group(1))
            episode = int(m_se.group(2))
        else:
            season = int(m_se.group(3))
            episode = int(m_se.group(4))

        t_before = t[:m_se.start()].strip(" -_.")
        if not t_before:
            title = t[m_se.end():].strip(" -_.")
        else:
            title = t_before
    else:
        # Caso 2: Temporada explicita 'Temporada 3 - 01' o 'Season 2'
        m_s = re.search(r"(?i)\b(?:temporada|temp|season|t)\s*(\d{1,2})\b", t)
        if m_s:
            season = int(m_s.group(1))
            title = t[:m_s.start()].strip(" -_.")
            after = t[m_s.end():]
            m_e = re.search(r"\b(\d{1,3})\b", after)
            if m_e:
                episode = int(m_e.group(1))
        else:
            # Caso 3: 'Capitulo 176' / 'Episodio 12' / 'Cap 01'
            m_cap = re.search(r"(?i)\b(?:cap[íi]tulo|cap|episodio|ep)\s*(\d{1,4})\b", t)
            if m_cap:
                episode = int(m_cap.group(1))
                title = t[:m_cap.start()].strip(" -_.")
            else:
                # Caso 4: Prefijo '001 Bleach'
                m_pref = re.match(r"^\s*(\d{1,3})\s+([a-zA-Z].*)$", t)
                if m_pref:
                    episode = int(m_pref.group(1))
                    title = m_pref.group(2).strip(" -_.")
                else:
                    # Caso 5: ' - 01 '
                    m_dash = re.search(r"\s*-\s*(\d{1,4})\b", t)
                    if m_dash:
                        episode = int(m_dash.group(1))
                        title = t[:m_dash.start()].strip(" -_.")
                    else:
                        # Caso 6: Sufijo ' 001'
                        m_suf = re.search(r"\s+(\d{1,3})\s*$", t)
                        if m_suf:
                            episode = int(m_suf.group(1))
                            title = t[:m_suf.start()].strip(" -_.")
                        else:
                            title = t.strip(" -_.")

    # Normalización del título de la serie
    title = re.sub(r"\((?:19|20)\d\d\)", "", title)  # quitar años
    # Quitar sufijos de temporada residuales en el título (ej: 2nd Season, Temporada 2, etc.)
    m_s2 = re.search(r"(?i)\b(\d{1,2})(?:st|nd|rd|th)?\s*season\b", title)
    if m_s2:
        season = int(m_s2.group(1))
        title = re.sub(r"(?i)\b\d{1,2}(?:st|nd|rd|th)?\s*season\b", "", title).strip()

    title = re.sub(r"(?i)\b(?:temporada|temp|season|t)\s*\d{1,2}\b", "", title).strip()
    title = re.sub(r"(?i)\b(?:parte|part)\s*\d{1,2}\b", "", title).strip()
    
    # Consolidaciones especiales
    if title.lower().startswith("gargoyles"):
        title = "Gargoyles"

    title = re.sub(r"[-_.]+", " ", title).strip()
    title = re.sub(r"\s{2,}", " ", title).strip()
    clean_title = title.title()

    return clean_title, season, episode, is_movie

async def main():
    if not os.path.exists(CONFIG_FILE):
        logger.error(f"No existe {CONFIG_FILE}")
        return

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    source_chat_id = config.get("source_chat_id", -1002257262928)
    topic_id = config.get("source_topic_id", 316312)

    logger.info(f"Conectando a Telegram para indexar topic {topic_id} en {source_chat_id}...")
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        source_entity = await client.get_entity(source_chat_id)
        logger.info(f"Entidad origen resuelta: {getattr(source_entity, 'title', source_chat_id)}")

        series_index = defaultdict(lambda: {
            "seasons": set(),
            "episodes": [],
            "sample_files": []
        })

        total_scanned = 0
        total_videos = 0
        total_movies_skipped = 0

        async for msg in client.iter_messages(
            source_entity,
            reply_to=topic_id,
            limit=None,
            reverse=True
        ):
            total_scanned += 1
            if total_scanned % 3000 == 0:
                logger.info(f"Escaneados {total_scanned} mensajes... ({total_videos} videos clasificados, {len(series_index)} series)")

            if not is_video_message(msg):
                continue

            total_videos += 1
            fn = extract_file_name(msg)
            caption = msg.raw_text or ""
            duration = get_video_duration(msg)
            size_mb = round(get_media_size(msg) / (1024 * 1024), 2)

            title, season, episode, is_movie = parse_anime_info(fn, caption)

            # Si es pelicula por duracion (>= 50 min sin capitulo) o etiqueta
            if is_movie or (duration >= 3000 and episode is None):
                total_movies_skipped += 1
                continue

            # Descartar titulos genericos o no validos
            if not title or len(title) < 3 or title.lower() in ("desconocido", "video", "anime", "episodio", "capitulo"):
                continue

            entry = series_index[title]
            entry["seasons"].add(season)
            if fn and len(entry["sample_files"]) < 3 and fn not in entry["sample_files"]:
                entry["sample_files"].append(fn)

            entry["episodes"].append({
                "id": msg.id,
                "season": season,
                "episode": episode if episode is not None else 0,
                "filename": fn,
                "size_mb": size_mb
            })

        logger.info(f"Escaneo finalizado: {total_scanned} msgs | {total_videos} videos | {total_movies_skipped} películas excluidas.")

        # Consolidar y filtrar series válidas (mínimo 3 episodios)
        series_consolidadas = []
        for s_title, data in series_index.items():
            ep_list = data["episodes"]
            if len(ep_list) < 3:
                # Omitir capitulos sueltos / series huerfanas
                continue

            # Ordenar episodios estrictamente por Temporada, Episodio y luego ID
            ep_list_sorted = sorted(ep_list, key=lambda x: (x["season"], x["episode"], x["id"]))

            total_size_gb = round(sum(e["size_mb"] for e in ep_list_sorted) / 1024, 2)
            seasons_sorted = sorted(list(data["seasons"]))

            series_consolidadas.append({
                "title": s_title,
                "total_episodes": len(ep_list_sorted),
                "seasons": seasons_sorted,
                "total_gb": total_size_gb,
                "sample_files": data["sample_files"],
                "episodes": ep_list_sorted
            })

        # Ordenar series por cantidad de episodios (de mayor a menor)
        series_consolidadas.sort(key=lambda x: x["total_episodes"], reverse=True)

        logger.info(f"✨ Series consolidadas verificadas (>= 3 caps): {len(series_consolidadas)}")
        total_caps = sum(s["total_episodes"] for s in series_consolidadas)
        logger.info(f"✨ Total episodios listos para sincronizar: {total_caps}")

        # Guardar en archivo JSON de índice
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(series_consolidadas, f, indent=2, ensure_ascii=False)
        logger.info(f"Guardado índice en {INDEX_FILE}")

        # Generar Reporte Markdown
        md = []
        md.append("# ⛩️ Catálogo e Índice Maestro de Series Anime Verificadas")
        md.append(f"\n- **Total de Series Verificadas:** {len(series_consolidadas)} series (1 tema único por serie).")
        md.append(f"- **Total de Episodios Asignados:** {total_caps} episodios exactos (sin mezclas ni rangos).")
        md.append(f"- **Películas Excluidas (ya en canal de películas):** {total_movies_skipped} archivos.\n")
        md.append("| # | Serie (Tema Único en Foro) | Temporadas | Episodios | Tamaño (GB) | Muestra de Archivos |")
        md.append("|---|----------------------------|:----------:|:---------:|:-----------:|---------------------|")

        for idx, s in enumerate(series_consolidadas, 1):
            seasons_str = f"T{', T'.join(map(str, s['seasons']))}"
            samples_str = "<br>".join(f"`{sf}`" for sf in s["sample_files"])
            md.append(f"| {idx} | **{s['title']}** | {seasons_str} | **{s['total_episodes']}** | {s['total_gb']} GB | {samples_str} |")

        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(md))
        logger.info(f"Guardado informe en {REPORT_FILE}")

if __name__ == "__main__":
    asyncio.run(main())
