import os
import sys
import json
import asyncio
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("InspeccionarTemas")

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION = os.environ["TELEGRAM_STRING_SESSION"]
TARGET_CHAT = int(os.environ.get("SERIES_DEST_CHAT", "-1002097175258"))

TOPICS_TO_INSPECT = [24884, 24995, 25026, 25064, 24524]

async def main():
    logger.info("Conectando a Telegram...")
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        chat = await client.get_entity(TARGET_CHAT)
        logger.info(f"Chat conectado: {chat.title} ({chat.id})")

        report = {}
        for tid in TOPICS_TO_INSPECT:
            logger.info(f"Inspeccionando tema ID {tid}...")
            msgs_info = []
            async for m in client.iter_messages(chat, reply_to=tid, limit=100):
                fname = m.file.name if m.file and hasattr(m.file, 'name') else None
                msgs_info.append({
                    "id": m.id,
                    "date": str(m.date),
                    "file_name": fname,
                    "text": (m.text or "")[:120],
                    "media_type": type(m.media).__name__ if m.media else "None"
                })

            report[tid] = {
                "count": len(msgs_info),
                "messages": msgs_info
            }
            logger.info(f"  Tema {tid}: {len(msgs_info)} mensajes recuperados.")

        with open("diagnostico_temas_afectados.json", "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        logger.info("Reporte guardado en diagnostico_temas_afectados.json")

if __name__ == "__main__":
    asyncio.run(main())
