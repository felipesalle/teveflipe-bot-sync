import asyncio
import json
import logging
import os
import re
from collections import defaultdict
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetForumTopicsRequest
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

from sync_bot import clean_series_title, is_junk_series_title, is_video_message, extract_file_name

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("explorar_grupo")

API_ID = int(os.getenv("TELEGRAM_API_ID") or os.getenv("API_ID") or 0)
API_HASH = os.getenv("TELEGRAM_API_HASH") or os.getenv("API_HASH") or ""
STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION") or ""
TARGET_CHAT_ID = int(os.getenv("TARGET_CHAT_ID", "-1002160549536"))

def extract_season_and_cap(filename: str):
    m = re.search(r"(?i)\b(?:S(\d+)|T(\d+)|(\d+)[xX](\d+)|Temporada\s*(\d+))\b", filename)
    season = None
    if m:
        for g in [m.group(1), m.group(2), m.group(3), m.group(5)]:
            if g:
                season = int(g)
                break
    return season

async def explore_group():
    if not STRING_SESSION:
        logger.error("TELEGRAM_STRING_SESSION no configurada.")
        return

    logger.info(f"Conectando a Telegram para explorar el chat: {TARGET_CHAT_ID}...")
    async with TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH) as client:
        logger.info("Cargando lista de diálogos para resolver entidades recientes...")
        entity = None
        async for dialog in client.iter_dialogs(limit=100):
            d_id = dialog.id
            if d_id == TARGET_CHAT_ID or str(TARGET_CHAT_ID) in str(d_id) or "4455579909" in str(d_id):
                entity = dialog.entity
                logger.info(f"¡Grupo encontrado en diálogos!: {dialog.title} (ID {d_id})")
                break
        
        if not entity:
            try:
                entity = await client.get_entity(TARGET_CHAT_ID)
            except Exception as e:
                logger.error(f"No se pudo resolver la entidad {TARGET_CHAT_ID}: {e}")
                return
        input_peer = await client.get_input_entity(entity)
        chat_title = getattr(entity, "title", "Desconocido")

        res = await client(GetForumTopicsRequest(
            peer=input_peer,
            offset_date=None,
            offset_id=0,
            offset_topic=0,
            limit=100
        ))

        topics = [t for t in res.topics if getattr(t, "id", 0) != 1]
        
        report_data = {
            "chat_title": chat_title,
            "chat_id": TARGET_CHAT_ID,
            "categories": {}
        }

        for top in topics:
            t_id = top.id
            t_title = top.title
            logger.info(f"Escaneando tema '{t_title}' (ID {t_id})...")
            
            series_in_topic = defaultdict(lambda: {"episodios": 0, "muestras": []})
            current_detected_title = None

            # Escanear los últimos 400 mensajes de cada tema
            async for m in client.iter_messages(entity, reply_to=t_id, limit=400):
                text = m.text or ""
                fname = extract_file_name(m)
                
                # 1. Mensaje de anuncio o carátula
                if text and (not m.media or isinstance(m.media, MessageMediaPhoto)):
                    cand = clean_series_title(text, is_filename=False)
                    if cand and not is_junk_series_title(cand):
                        current_detected_title = cand
                
                # 2. Archivo de video
                if is_video_message(m):
                    stitle = clean_series_title(fname, is_filename=True) if fname else None
                    if not stitle or is_junk_series_title(stitle):
                        stitle = current_detected_title or "Sin clasificar"
                    
                    series_in_topic[stitle]["episodios"] += 1
                    if len(series_in_topic[stitle]["muestras"]) < 2 and fname:
                        series_in_topic[stitle]["muestras"].append(fname)

            report_data["categories"][t_title] = {
                "id": t_id,
                "series": {k: v for k, v in series_in_topic.items() if v["episodios"] > 0}
            }

        # Guardar en Markdown
        with open("EXPLORACION_DETALLADA.md", "w", encoding="utf-8") as f:
            f.write(f"# 📂 Catálogo Detallado: **{chat_title}**\n\n")
            f.write(f"- **ID del Chat:** `{TARGET_CHAT_ID}`\n")
            f.write(f"- **Tipo:** Grupo con Foros por Categoría Temática\n\n")
            
            for cat_name, cdata in report_data["categories"].items():
                f.write(f"## 📁 Tema: **{cat_name}** (ID: `{cdata['id']}`)\n\n")
                if not cdata["series"]:
                    f.write("*No se detectaron series recientes o está vacío.*\n\n")
                    continue
                f.write("| # | Serie Detectada | Episodios Recientes | Archivo de Muestra |\n")
                f.write("|---|-----------------|---------------------|--------------------|\n")
                for i, (sname, sinfo) in enumerate(sorted(cdata["series"].items()), 1):
                    sample = sinfo["muestras"][0] if sinfo["muestras"] else "N/A"
                    f.write(f"| {i} | **{sname}** | {sinfo['episodios']} caps | `{sample}` |\n")
                f.write("\n---\n\n")

        with open("exploracion_detallada.json", "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        logger.info("Exploración detallada terminada.")

if __name__ == "__main__":
    asyncio.run(explore_group())
