import asyncio
import json
import logging
import os
import re
from collections import defaultdict
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaDocument, DocumentAttributeFilename, DocumentAttributeVideo

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("ScanSeriesInfantiles")

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION", "")

CANAL_SERIES_ID = int(os.getenv("CANAL_SERIES_ID", "-1003874872975"))

CLEAN_TAGS_REGEX = re.compile(
    r"(?i)\b(1080p|720p|480p|4k|2160p|bluray|bdrip|web-?dl|webrip|dvdrip|hdtv|tvrip|x264|x265|hevc|h264|h265|aac|ac3|dts|dual|latino|castellano|espanol|spanish|subtitulado|sub|subs|vose|hd|rip|xvid|divx|flv|mp4|mkv|avi)\b"
)

SERIES_SEASON_EP_REGEX = re.compile(
    r"(?i)(?:[sS](\d{1,2})[eE](\d{1,3})|(\d{1,2})x(\d{1,3})|\b(?:cap[íi]tulo|cap|episodio|ep)\s*(\d{1,3})\b|\bT(\d{1,2})\b|\b(?:temp|temporada)\s*(\d{1,2})\b)",
    re.IGNORECASE
)

TRAILING_NUM_REGEX = re.compile(r"[-–—_]\s*(\d{1,3})\s*$", re.IGNORECASE)


def extract_filename(msg) -> str:
    if getattr(msg, "file", None) and getattr(msg.file, "name", None):
        return msg.file.name or ""
    if msg.media and isinstance(msg.media, MessageMediaDocument) and msg.media.document:
        for attr in msg.media.document.attributes:
            if isinstance(attr, DocumentAttributeFilename):
                return attr.file_name or ""
    return ""


def clean_series_name(raw_name: str, caption: str = "") -> tuple:
    """Extrae el nombre limpio de la serie, temporada y capítulo."""
    cand = raw_name
    if not cand and caption:
        cand = caption.split("\n")[0].strip()
    if not cand:
        return "Desconocido", None, None

    # Quitar extensión
    name = re.sub(r"\.[a-zA-Z0-9]{2,4}$", "", cand)
    # Reemplazar separadores comunes
    name = name.replace(".", " ").replace("_", " ")

    # Detectar temporada y episodio
    season = None
    episode = None
    m = SERIES_SEASON_EP_REGEX.search(name)
    if m:
        g = m.groups()
        if g[0] and g[1]:
            season, episode = int(g[0]), int(g[1])
        elif g[2] and g[3]:
            season, episode = int(g[2]), int(g[3])
        elif g[4]:
            episode = int(g[4])
        elif g[5]:
            season = int(g[5])
        elif g[6]:
            season = int(g[6])
        name = name[:m.start()].strip()
    else:
        # Check trailing number (ej: "Fraggle Rock - 05")
        tm = TRAILING_NUM_REGEX.search(name)
        if tm:
            episode = int(tm.group(1))
            name = name[:tm.start()].strip()

    # Limpiar año entre paréntesis o suelto
    name = re.sub(r"\b(19\d\d|20\d\d)\b", "", name)
    # Limpiar tags técnicas
    name = CLEAN_TAGS_REGEX.replace("", name)
    # Limpiar signos y corchetes
    name = re.sub(r"[\[\]\(\)\{\}\-–—+!¡?¿]+", " ", name)
    # Normalizar espacios
    clean_title = re.sub(r"\s+", " ", name).strip()

    # Title-case estético
    if clean_title:
        words = clean_title.split()
        clean_title = " ".join(w.capitalize() if not w.isupper() else w for w in words)
    else:
        clean_title = "Sin Título"

    return clean_title, season, episode


async def scan():
    if not STRING_SESSION:
        logger.error("TELEGRAM_STRING_SESSION no configurada.")
        return

    logger.info("Iniciando escaneo de Series Infantiles...")
    async with TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH) as client:
        channel = await client.get_entity(CANAL_SERIES_ID)
        logger.info(f"Conectado a canal: {channel.title} (ID: {CANAL_SERIES_ID})")

        series_data = defaultdict(lambda: {
            "count": 0,
            "seasons": set(),
            "sample_episodes": []
        })

        total_msgs = 0
        async for msg in client.iter_messages(channel, limit=None):
            if not msg or not msg.media:
                continue
            total_msgs += 1
            fname = extract_filename(msg)
            caption = msg.raw_text or ""
            title, season, ep = clean_series_name(fname, caption)

            entry = series_data[title]
            entry["count"] += 1
            if season:
                entry["seasons"].add(season)
            if len(entry["sample_episodes"]) < 3 and fname:
                entry["sample_episodes"].append(fname)

            if total_msgs % 2000 == 0:
                logger.info(f"Escaneados {total_msgs} mensajes... ({len(series_data)} series detectadas)")

        logger.info(f"Escaneo finalizado. Total mensajes: {total_msgs}. Series distintas: {len(series_data)}")

        # Convertir a estructura serializable
        catalog_list = []
        for title, info in series_data.items():
            catalog_list.append({
                "title": title,
                "episode_count": info["count"],
                "seasons": sorted(list(info["seasons"])),
                "samples": info["sample_episodes"]
            })

        catalog_list.sort(key=lambda x: x["episode_count"], reverse=True)

        # 1. Guardar JSON
        json_file = "catalogo_series_infantiles.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump({
                "total_messages_scanned": total_msgs,
                "total_series_count": len(catalog_list),
                "series": catalog_list
            }, f, indent=2, ensure_ascii=False)
        logger.info(f"Catálogo JSON guardado en {json_file}")

        # 2. Guardar Markdown para visualización amigable
        md_file = "CATALOGO_SERIES_INFANTILES.md"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write("# 📺 Catálogo Completo de Series Infantiles\n\n")
            f.write(f"- **Total Episodios Escaneados:** {total_msgs:,}\n")
            f.write(f"- **Total Series Detectadas:** {len(catalog_list):,}\n\n")
            f.write("## 🏆 Top Series con Mayor Número de Capítulos\n\n")
            f.write("| # | Nombre de la Serie | Capítulos | Temporadas Detectadas | Muestra de Archivo |\n")
            f.write("|---|---|---|---|---|\n")
            for idx, s in enumerate(catalog_list, start=1):
                seasons_str = ", ".join(f"T{sn}" for sn in s["seasons"]) if s["seasons"] else "General"
                sample_str = s["samples"][0] if s["samples"] else "-"
                # Truncar sample si es muy largo
                if len(sample_str) > 45:
                    sample_str = sample_str[:42] + "..."
                f.write(f"| {idx} | **{s['title']}** | {s['episode_count']} | {seasons_str} | `{sample_str}` |\n")

        logger.info(f"Catálogo Markdown guardado en {md_file}")


if __name__ == "__main__":
    asyncio.run(scan())
