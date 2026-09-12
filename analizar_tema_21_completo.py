import asyncio
import json
import logging
import os
import sys
from collections import defaultdict
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaPhoto

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("analizar_tema_21_completo")

API_ID = int(os.getenv("TELEGRAM_API_ID") or os.getenv("API_ID") or 0)
API_HASH = os.getenv("TELEGRAM_API_HASH") or os.getenv("API_HASH") or ""
STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION") or ""
TARGET_CHAT_ID = int(os.getenv("TARGET_CHAT_ID", "-1002160549536"))
TOPIC_ID = 21

async def scan_all_series_in_topic_21():
    if not STRING_SESSION:
        logger.error("TELEGRAM_STRING_SESSION no configurada.")
        return

    async with TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH) as client:
        entity = await client.get_entity(TARGET_CHAT_ID)
        
        logger.info("Escaneando todas las carátulas, anuncios y cabeceras de series del Tema 21...")
        
        series_found = []
        # Leemos todos los mensajes que tengan texto o foto en el Tema 21 desde el inicio
        count = 0
        async for msg in client.iter_messages(entity, reply_to=TOPIC_ID, reverse=True, limit=None):
            count += 1
            if count % 2000 == 0:
                logger.info(f"Procesados {count} mensajes... (Msg ID: {msg.id})")
                
            text = (msg.text or "").strip()
            if not text:
                continue
                
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            if not lines:
                continue
                
            # Detectar si es una ficha técnica de serie
            is_fiche = any(kw in text.lower() for kw in [
                "filmaffinity", "temporadas", "capítulos", "reparto:", 
                "serie de tv", "género", "sinopsis"
            ]) and not text.startswith("🔴") and not text.lower().startswith("temporada")
            
            if is_fiche or ("**" in lines[0] and len(lines) > 2 and "temp" in text.lower()):
                title_line = lines[0]
                series_found.append({
                    "id": msg.id,
                    "first_line": title_line,
                    "full_text": text
                })

        logger.info(f"Escaneo completo terminado. Total mensajes analizados: {count}")
        logger.info(f"Total cabeceras de series encontradas: {len(series_found)}")

        with open("todas_series_tema_21.json", "w", encoding="utf-8") as f:
            json.dump(series_found, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    asyncio.run(scan_all_series_in_topic_21())
