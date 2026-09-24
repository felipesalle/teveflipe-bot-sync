import asyncio
import json
import logging
import os
import re
import sys
import unicodedata
from collections import defaultdict
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto, DocumentAttributeFilename, DocumentAttributeVideo

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("AuditoriaSeriesAsiaticas")

API_ID = int(os.getenv("TELEGRAM_API_ID") or 0)
API_HASH = os.getenv("TELEGRAM_API_HASH") or ""
STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION") or ""

TARGET_CHAT_ID = int(os.getenv("TARGET_CHAT_ID", "-1002160549536"))
TOPIC_ID = int(os.getenv("TOPIC_ID", "10"))

VIDEO_EXTENSIONS = (".mkv", ".mp4", ".avi", ".mov", ".webm", ".ts", ".m4v")

def is_video_message(message) -> bool:
    if not message or not message.media:
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
    if not message:
        return ""
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

def normalize_title(title: str) -> str:
    if not title:
        return ""
    t = title.strip()
    t = re.sub(r"\[.*?\]|\(.*?\)", "", t)
    t = t.replace("_", " ").replace(".", " ").replace("-", " ")
    t = re.sub(r"\s+", " ", t).strip()
    # Normalize accents for matching key
    return t.title()

def parse_episode_filename(fn: str):
    clean = re.sub(r"\.[a-zA-Z0-9]{2,4}$", "", fn).strip()
    if re.match(r"^\d+$", clean):
        return None, 1, int(clean)
        
    spaced = clean.replace("_", " ").replace(".", " ")
    
    # S01E02 or 1x02
    m1 = re.search(r"(?i)\b(?:S(\d+)\s*E(\d+)|(\d+)\s*[xX×]\s*(\d+))\b", spaced)
    if m1:
        s = int(m1.group(1) or m1.group(3))
        e = int(m1.group(2) or m1.group(4))
        title = clean[:m1.start()].strip(" _-.")
        return title, s, e
        
    # Temporada X Episodio Y
    m2 = re.search(r"(?i)\b(?:Temporada|Temp|T)\s*(\d+)\s*(?:Episodio|Cap[ií]tulo|Cap|Ep)?\s*(\d+)\b", spaced)
    if m2:
        s = int(m2.group(1))
        e = int(m2.group(2))
        title = clean[:m2.start()].strip(" _-.")
        return title, s, e

    # Cap / Ep X
    m_cap = re.search(r"(?i)\b(?:Cap[ií]tulo|Episodio|Cap|Ep)\s*(\d+)\b", spaced)
    if m_cap:
        e = int(m_cap.group(1))
        title = clean[:m_cap.start()].strip(" _-.")
        return title, 1, e
        
    # Standalone number: <Title> 01 (2025)... or <Title> 12 FIN
    m3 = re.search(r"\b(0[1-9]|[1-9]\d{0,2})\b", spaced)
    if m3:
        before = clean[:m3.start()].strip(" _-.")
        if any(c.isalpha() for c in before) and len(before) >= 3:
            e = int(m3.group(1))
            return before, 1, e

    return clean, 1, None

def extract_header_title(text: str) -> str:
    if not text:
        return ""
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    if not lines:
        return ""
    
    # Common header formats
    first = lines[0]
    # Remove leading decorative emojis
    first = re.sub(r"^[\U00010000-\U0010ffff\u2600-\u27bf\u2300-\u23ff\u2b50\u2b55\ufe0f\s*🔴🎬📺📁👉]+", "", first)
    first = first.replace("**", "").replace("__", "").strip()
    
    # Check if lines have "Título:" or "Titulo:"
    for l in lines:
        m = re.match(r"(?i)^(?:t[ií]tulo|t[ií]tulo original|serie):\s*(.+)$", l)
        if m:
            cand = m.group(1).replace("**", "").strip()
            if cand:
                return cand

    # Remove extra tags
    first = re.sub(r"(?i)\b(?:serie|dorama|k-drama|kdrama|temporada\s*\d+|completa|castellano|latino|audio)\b.*$", "", first).strip()
    return first

async def main():
    if not STRING_SESSION:
        logger.error("TELEGRAM_STRING_SESSION no configurada.")
        sys.exit(1)

    logger.info(f"Conectando a Telegram para auditar chat {TARGET_CHAT_ID}, Tema {TOPIC_ID}...")
    async with TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH) as client:
        # Resolve target chat
        entity = None
        async for dialog in client.iter_dialogs(limit=100):
            if dialog.id == TARGET_CHAT_ID or str(TARGET_CHAT_ID) in str(dialog.id):
                entity = dialog.entity
                logger.info(f"Chat encontrado en diálogos: {dialog.title}")
                break

        if not entity:
            entity = await client.get_entity(TARGET_CHAT_ID)

        chat_title = getattr(entity, "title", "Supergrupo")
        logger.info(f"Chat resuelto: '{chat_title}' (ID: {TARGET_CHAT_ID})")

        # Data structure for series
        # series_db[series_key] = {
        #     "title": display_title,
        #     "header_text": "",
        #     "poster_msg_id": None,
        #     "seasons": { season_num: { ep_num: [ep_info] } },
        #     "total_size_bytes": 0,
        #     "files": []
        # }
        series_db = {}
        
        current_header = ""
        current_poster_id = None
        current_header_text = ""

        total_msgs = 0
        video_count = 0
        poster_count = 0

        logger.info("Iniciando escaneo cronológico completo del Tema 10 (Series Asiáticas)...")
        async for msg in client.iter_messages(entity, reply_to=TOPIC_ID, reverse=True, limit=None):
            total_msgs += 1
            if total_msgs % 100 == 0:
                logger.info(f"Leídos {total_msgs} mensajes en el tema... (ID actual: {msg.id})")

            text = (msg.text or "").strip()

            # 1. Detection of series banner / header / card
            is_fiche = False
            if text:
                low_text = text.lower()
                is_fiche = any(kw in low_text for kw in [
                    "filmaffinity", "temporadas", "capítulos", "capitulos",
                    "reparto", "serie de tv", "género", "genero", "sinopsis", "dorama"
                ])
                # Or a bold short line introducing a series
                if not is_fiche and ("**" in text or text.startswith("🎬") or text.startswith("📺")):
                    lines = [l.strip() for l in text.split("\n") if l.strip()]
                    if len(lines) <= 5 and any(c.isalpha() for c in lines[0]):
                        is_fiche = True

            if is_fiche or (msg.media and isinstance(msg.media, MessageMediaPhoto) and text):
                cand_title = extract_header_title(text)
                if cand_title and len(cand_title) >= 3:
                    current_header = cand_title
                    current_poster_id = msg.id
                    current_header_text = text
                    poster_count += 1
                    # Initialize in DB if not present
                    key = normalize_title(current_header)
                    if key not in series_db:
                        series_db[key] = {
                            "title": current_header,
                            "header_text": current_header_text,
                            "poster_msg_id": current_poster_id,
                            "seasons": defaultdict(lambda: defaultdict(list)),
                            "total_size_bytes": 0,
                            "files": []
                        }

            # 2. Detection of video message
            if is_video_message(msg):
                video_count += 1
                fn = extract_file_name(msg)
                sz = get_media_size(msg)
                
                title_from_fn, season_num, ep_num = parse_episode_filename(fn) if fn else (None, 1, None)
                
                # Determine target series
                series_name = None
                if title_from_fn and len(title_from_fn) >= 3:
                    series_name = title_from_fn
                elif current_header:
                    series_name = current_header
                else:
                    series_name = "Sin Título / Miscelánea"

                key = normalize_title(series_name)
                if key not in series_db:
                    series_db[key] = {
                        "title": series_name,
                        "header_text": current_header_text if current_header else "",
                        "poster_msg_id": current_poster_id if current_header else None,
                        "seasons": defaultdict(lambda: defaultdict(list)),
                        "total_size_bytes": 0,
                        "files": []
                    }

                ep_info = {
                    "msg_id": msg.id,
                    "date": msg.date.isoformat() if msg.date else "",
                    "file_name": fn,
                    "size_bytes": sz,
                    "season": season_num,
                    "episode": ep_num
                }

                series_db[key]["seasons"][season_num][ep_num].append(ep_info)
                series_db[key]["total_size_bytes"] += sz
                series_db[key]["files"].append(fn)

        logger.info(f"Escaneo finalizado. Total mensajes: {total_msgs}, Videos: {video_count}, Fichas/Pósters: {poster_count}")
        logger.info(f"Total series identificadas: {len(series_db)}")

        # Convert to serializable structure
        export_series = []
        for key, sdata in sorted(series_db.items(), key=lambda x: x[1]["title"].lower()):
            total_caps = sum(len(eps) for season, eps in sdata["seasons"].items())
            if total_caps == 0:
                continue

            seasons_summary = {}
            for s_num, eps_dict in sorted(sdata["seasons"].items()):
                known_eps = [e for e in eps_dict.keys() if e is not None]
                none_eps = len(eps_dict.get(None, []))
                min_ep = min(known_eps) if known_eps else None
                max_ep = max(known_eps) if known_eps else None
                
                # Check for missing episodes
                missing = []
                if min_ep and max_ep and len(known_eps) > 1:
                    full_range = set(range(min_ep, max_ep + 1))
                    missing = sorted(list(full_range - set(known_eps)))

                seasons_summary[f"Temporada {s_num}"] = {
                    "episodios_contabilizados": len(known_eps) + none_eps,
                    "rango_detectado": f"{min_ep} a {max_ep}" if min_ep and max_ep else f"{len(known_eps) + none_eps} caps",
                    "faltantes": missing,
                    "episodios_detalle": [
                        {
                            "capitulo": ep_k,
                            "archivos": [e["file_name"] for e in ep_list],
                            "msg_ids": [e["msg_id"] for e in ep_list]
                        }
                        for ep_k, ep_list in sorted(eps_dict.items(), key=lambda x: (x[0] is None, x[0]))
                    ]
                }

            export_series.append({
                "titulo": sdata["title"],
                "total_capitulos": total_caps,
                "tamano_gb": round(sdata["total_size_bytes"] / (1024**3), 2),
                "poster_msg_id": sdata["poster_msg_id"],
                "temporadas": seasons_summary,
                "muestras": sdata["files"][:3]
            })

        # Generate JSON
        result_json = {
            "chat_title": chat_title,
            "chat_id": TARGET_CHAT_ID,
            "topic_id": TOPIC_ID,
            "topic_name": "Series asiáticas",
            "total_mensajes_escaneados": total_msgs,
            "total_videos_encontrados": video_count,
            "total_series": len(export_series),
            "total_episodios_acumulados": sum(s["total_capitulos"] for s in export_series),
            "total_peso_gb": round(sum(s["tamano_gb"] for s in export_series), 2),
            "series": export_series
        }

        with open("auditoria_series_asiaticas.json", "w", encoding="utf-8") as f:
            json.dump(result_json, f, indent=2, ensure_ascii=False)
        logger.info("Guardado auditoria_series_asiaticas.json")

        # Generate Markdown Report
        with open("AUDITORIA_SERIES_ASIATICAS.md", "w", encoding="utf-8") as f:
            f.write("# 📊 Auditoría Completa: **Series Asiáticas (Tema 10)**\n\n")
            f.write(f"- **Canal / Supergrupo Origen:** `{chat_title}` (`{TARGET_CHAT_ID}`)\n")
            f.write(f"- **Tema / Foro:** `Series asiáticas` (ID: `{TOPIC_ID}`)\n")
            f.write(f"- **Total Series Identificadas:** **{len(export_series)}**\n")
            f.write(f"- **Total Capítulos:** **{result_json['total_episodios_acumulados']}**\n")
            f.write(f"- **Espacio Total en Disco:** **{result_json['total_peso_gb']} GB**\n")
            f.write(f"- **Total Mensajes Escaneados:** **{total_msgs}**\n\n")
            f.write("---\n\n")

            f.write("## 📋 Resumen Rápido por Serie\n\n")
            f.write("| # | Título de la Serie | Capítulos | Temporadas | Peso Total | Estado |\n")
            f.write("|---|--------------------|-----------|------------|------------|--------|\n")

            for i, s in enumerate(export_series, 1):
                temps_str = ", ".join([f"{t}: {info['episodios_contabilizados']} caps" for t, info in s["temporadas"].items()])
                has_missing = any(len(info["faltantes"]) > 0 for info in s["temporadas"].values())
                estado = "⚠️ Faltan caps" if has_missing else "✅ Completa"
                f.write(f"| {i} | **{s['titulo']}** | {s['total_capitulos']} | {temps_str} | {s['tamano_gb']} GB | {estado} |\n")

            f.write("\n---\n\n")
            f.write("## 🔍 Detalle Exhaustivo de Cada Serie\n\n")

            for i, s in enumerate(export_series, 1):
                f.write(f"### {i}. **{s['titulo']}**\n\n")
                f.write(f"- **Capítulos:** {s['total_capitulos']}\n")
                f.write(f"- **Peso:** {s['tamano_gb']} GB\n")
                if s["poster_msg_id"]:
                    f.write(f"- **Mensaje Ficha/Póster:** Msg ID `{s['poster_msg_id']}`\n")

                for t_name, t_info in s["temporadas"].items():
                    f.write(f"#### 🎬 {t_name} ({t_info['episodios_contabilizados']} capítulos)\n")
                    f.write(f"- Rango detectado: `{t_info['rango_detectado']}`\n")
                    if t_info["faltantes"]:
                        f.write(f"- ⚠️ **Episodios faltantes en el rango:** `{t_info['faltantes']}`\n")
                    else:
                        f.write("- ✅ Secuencia correlativa completa sin huecos.\n")
                    
                    f.write("\n**Muestra de archivos y episodios:**\n")
                    for ep in t_info["episodios_detalle"][:10]:
                        fn_str = ep["archivos"][0] if ep["archivos"] else "N/A"
                        ep_label = f"Capítulo {ep['capitulo']}" if ep['capitulo'] is not None else "Capítulo Especial / Sin número"
                        f.write(f"  - `{ep_label}`: {fn_str} *(ID {ep['msg_ids'][0]})*\n")
                    if len(t_info["episodios_detalle"]) > 10:
                        f.write(f"  - *...y {len(t_info['episodios_detalle']) - 10} capítulos más.*\n")
                    f.write("\n")
                f.write("\n---\n\n")

        logger.info("Guardado AUDITORIA_SERIES_ASIATICAS.md")

if __name__ == "__main__":
    asyncio.run(main())
