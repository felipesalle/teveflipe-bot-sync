import asyncio
import json
import logging
import os
import re
from typing import Dict, List, Optional
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

from sync_bot import clean_series_title, is_junk_series_title, is_video_message, extract_file_name

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("escanear_catalogo")

API_ID = int(os.getenv("TELEGRAM_API_ID") or os.getenv("API_ID") or 0)
API_HASH = os.getenv("TELEGRAM_API_HASH") or os.getenv("API_HASH") or ""
STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION") or ""

SERIES_SOURCE_CHAT = int(os.getenv("SERIES_SOURCE_CHAT", "-1002257262928"))
SERIES_SOURCE_TOPIC = int(os.getenv("SERIES_SOURCE_TOPIC", "157592"))


def extract_season_from_filename(filename: str) -> Optional[int]:
    """Extrae el número de temporada de un archivo si existe."""
    m = re.search(r"(?i)\b(?:S(\d+)|T(\d+)|(\d+)[xX]\d+|Temporada\s*(\d+))\b", filename)
    if m:
        for g in m.groups():
            if g:
                try:
                    return int(g)
                except ValueError:
                    pass
    return None


async def scan_source_catalog():
    if not STRING_SESSION:
        logger.error("TELEGRAM_STRING_SESSION no configurada.")
        return

    logger.info("Conectando a Telegram para escanear catálogo de series...")
    async with TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH) as client:
        source_chat = await client.get_input_entity(SERIES_SOURCE_CHAT)
        
        logger.info(f"Escaneando mensajes del chat {SERIES_SOURCE_CHAT} (Topic: {SERIES_SOURCE_TOPIC})...")
        
        # Leemos mensajes desde el inicio del tema en orden cronológico
        catalog: Dict[str, dict] = {}
        current_series = None
        
        total_scanned = 0
        async for msg in client.iter_messages(
            source_chat,
            reply_to=SERIES_SOURCE_TOPIC if SERIES_SOURCE_TOPIC else None,
            reverse=True,
            limit=4000
        ):
            total_scanned += 1
            text_content = msg.text or ""
            file_name = extract_file_name(msg)
            
            # 1. Mensaje de texto (anuncio de serie)
            if not msg.media and text_content:
                cand = clean_series_title(text_content, is_filename=False)
                if cand and not is_junk_series_title(cand):
                    current_series = cand
                    if current_series not in catalog:
                        catalog[current_series] = {
                            "titulo": current_series,
                            "temporadas": set(),
                            "episodios": 0,
                            "primer_id": msg.id,
                            "ultimo_id": msg.id
                        }
            
            # 2. Carátula o póster
            elif msg.media and isinstance(msg.media, MessageMediaPhoto):
                extracted = clean_series_title(text_content, is_filename=False) if text_content else None
                if extracted and not is_junk_series_title(extracted):
                    current_series = extracted
                    if current_series not in catalog:
                        catalog[current_series] = {
                            "titulo": current_series,
                            "temporadas": set(),
                            "episodios": 0,
                            "primer_id": msg.id,
                            "ultimo_id": msg.id
                        }
            
            # 3. Archivo de video
            elif is_video_message(msg):
                file_series = clean_series_title(file_name, is_filename=True) if file_name else None
                if file_series and not is_junk_series_title(file_series):
                    current_series = file_series
                
                if current_series:
                    if current_series not in catalog:
                        catalog[current_series] = {
                            "titulo": current_series,
                            "temporadas": set(),
                            "episodios": 0,
                            "primer_id": msg.id,
                            "ultimo_id": msg.id
                        }
                    
                    catalog[current_series]["episodios"] += 1
                    catalog[current_series]["ultimo_id"] = msg.id
                    season = extract_season_from_filename(file_name or text_content)
                    if season is not None:
                        catalog[current_series]["temporadas"].add(season)

        logger.info(f"Escaneo finalizado. Total de mensajes analizados: {total_scanned}")
        logger.info(f"Total de series detectadas: {len(catalog)}")
        
        # Preparar reporte
        series_list = []
        for name, data in catalog.items():
            if data["episodios"] == 0 and len(data["temporadas"]) == 0:
                continue
            temps = sorted(list(data["temporadas"]))
            temps_str = f"T{min(temps)}-T{max(temps)} ({len(temps)} temp.)" if len(temps) > 1 else (f"T{temps[0]}" if temps else "1 temp.")
            series_list.append({
                "titulo": name,
                "temporadas": temps,
                "temporadas_texto": temps_str,
                "episodios": data["episodios"],
                "rango_ids": [data["primer_id"], data["ultimo_id"]]
            })
            
        # Ordenar alfabéticamente
        series_list.sort(key=lambda x: x["titulo"].lower())
        
        # Guardar en JSON
        output_json = "catalogo_series.json"
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(series_list, f, indent=2, ensure_ascii=False)
        logger.info(f"Catálogo JSON guardado en {output_json}")
        
        # Guardar en Markdown legible
        output_md = "CATALOGO_SERIES.md"
        with open(output_md, "w", encoding="utf-8") as f:
            f.write("# 📺 Catálogo de Series Disponibles en el Grupo Fuente\n\n")
            f.write(f"*Total de series detectadas: **{len(series_list)}** (Analizados {total_scanned} mensajes)*\n\n")
            f.write("| # | Título de la Serie | Temporadas | Episodios | Rango de Mensajes |\n")
            f.write("|---|-------------------|------------|-----------|-------------------|\n")
            for idx, s in enumerate(series_list, 1):
                f.write(f"| {idx} | **{s['titulo']}** | {s['temporadas_texto']} | {s['episodios']} | `{s['rango_ids'][0]} - {s['rango_ids'][1]}` |\n")
        logger.info(f"Catálogo Markdown guardado en {output_md}")
        
        # Imprimir en stdout para que se vea directo en los logs de GitHub Actions
        print("\n" + "="*70)
        print(f"CATÁLOGO DE SERIES FUENTE ({len(series_list)} series encontradas)")
        print("="*70)
        for idx, s in enumerate(series_list, 1):
            print(f"{idx:3d}. {s['titulo']:<40} | {s['temporadas_texto']:<18} | {s['episodios']} caps")
        print("="*70 + "\n")


if __name__ == "__main__":
    asyncio.run(scan_source_catalog())
