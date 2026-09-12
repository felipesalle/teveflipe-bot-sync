import asyncio
import json
import logging
import os
import re
from collections import defaultdict
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

from sync_bot import clean_series_title, is_junk_series_title, is_video_message, extract_file_name

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("analizar_tema_21")

API_ID = int(os.getenv("TELEGRAM_API_ID") or os.getenv("API_ID") or 0)
API_HASH = os.getenv("TELEGRAM_API_HASH") or os.getenv("API_HASH") or ""
STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION") or ""
TARGET_CHAT_ID = int(os.getenv("TARGET_CHAT_ID", "-1002160549536"))
TOPIC_ID = 21

async def analyze_topic():
    if not STRING_SESSION:
        logger.error("TELEGRAM_STRING_SESSION no configurada.")
        return

    logger.info(f"Conectando a Telegram para analizar el tema {TOPIC_ID} del chat {TARGET_CHAT_ID}...")
    async with TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH) as client:
        entity = await client.get_entity(TARGET_CHAT_ID)
        
        # Vamos a leer todos los mensajes del tema 21 en orden cronológico (reverse=True)
        all_messages = []
        total_scanned = 0
        video_count = 0
        
        current_series = None
        series_data = defaultdict(lambda: {
            "titulo": "",
            "episodios": 0,
            "primer_id": None,
            "ultimo_id": None,
            "archivos": [],
            "temporadas_detectadas": set()
        })
        
        # Guardaremos también los mensajes de texto relevantes (anuncios)
        announcements = []

        async for msg in client.iter_messages(entity, reply_to=TOPIC_ID, reverse=True, limit=6000):
            total_scanned += 1
            text = (msg.text or "").strip()
            fname = extract_file_name(msg)
            
            # Anuncio o foto
            if text and (not msg.media or isinstance(msg.media, MessageMediaPhoto)):
                announcements.append({"id": msg.id, "text": text[:200]})
                cand = clean_series_title(text, is_filename=False)
                if cand and not is_junk_series_title(cand):
                    current_series = cand
            
            # Video
            if is_video_message(msg):
                video_count += 1
                cand_from_file = clean_series_title(fname, is_filename=True) if fname else None
                
                # Si el nombre del archivo es solo "Episodio XXX" o números, usar current_series
                if not cand_from_file or is_junk_series_title(cand_from_file) or cand_from_file.lower().startswith("episodio"):
                    stitle = current_series or "Desconocida (Solo número de episodio)"
                else:
                    stitle = cand_from_file
                    current_series = cand_from_file
                
                s = series_data[stitle]
                s["titulo"] = stitle
                s["episodios"] += 1
                if s["primer_id"] is None:
                    s["primer_id"] = msg.id
                s["ultimo_id"] = msg.id
                if len(s["archivos"]) < 5 and fname:
                    s["archivos"].append(fname)
                    
                # Detectar temporada
                m_seas = re.search(r"(?i)\b(?:S(\d+)|T(\d+)|(\d+)[xX]\d+|Temporada\s*(\d+))\b", fname or text)
                if m_seas:
                    for g in m_seas.groups():
                        if g:
                            try:
                                s["temporadas_detectadas"].add(int(g))
                            except ValueError:
                                pass

        logger.info(f"Escaneo finalizado. Total mensajes: {total_scanned}, Total videos: {video_count}")
        logger.info(f"Series encontradas: {len(series_data)}")

        # Preparar resultados
        results = []
        for stitle, s in series_data.items():
            temps = sorted(list(s["temporadas_detectadas"]))
            results.append({
                "titulo": stitle,
                "episodios": s["episodios"],
                "temporadas": temps,
                "rango_ids": [s["primer_id"], s["ultimo_id"]],
                "archivos_muestra": s["archivos"]
            })
            
        results.sort(key=lambda x: x["episodios"], reverse=True)

        # Escribir Markdown
        with open("ANALISIS_TEMA_21.md", "w", encoding="utf-8") as f:
            f.write("# 🇪🇸 Análisis Exhaustivo del Tema 21: Series Españolas (+100 cap)\n\n")
            f.write(f"- **Total mensajes leídos:** {total_scanned}\n")
            f.write(f"- **Total videos:** {video_count}\n")
            f.write(f"- **Total series detectadas:** {len(results)}\n\n")
            
            f.write("## 📺 Resumen de Series Encontradas\n\n")
            f.write("| # | Serie | Total Episodios | Temporadas | Archivos de Muestra |\n")
            f.write("|---|-------|-----------------|------------|---------------------|\n")
            for idx, r in enumerate(results, 1):
                t_str = f"T{min(r['temporadas'])}-T{max(r['temporadas'])}" if len(r['temporadas']) > 1 else (f"T{r['temporadas'][0]}" if r['temporadas'] else "N/A")
                samples = "<br>".join(f"`{a}`" for a in r["archivos_muestra"][:3])
                f.write(f"| {idx} | **{r['titulo']}** | {r['episodios']} | {t_str} | {samples} |\n")
                
            f.write("\n## 📝 Anuncios y Textos de Cabecera Encontrados\n\n")
            for a in announcements[:30]:
                f.write(f"- [Msg {a['id']}]: `{a['text']}`\n")

        with open("analisis_tema_21.json", "w", encoding="utf-8") as f:
            json.dump({
                "total_mensajes": total_scanned,
                "total_videos": video_count,
                "series": results,
                "anuncios": announcements
            }, f, indent=2, ensure_ascii=False)

        logger.info("Guardado en ANALISIS_TEMA_21.md")

if __name__ == "__main__":
    asyncio.run(analyze_topic())
