import asyncio
import os
import re
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaDocument, DocumentAttributeFilename, DocumentAttributeVideo

API_ID = int(os.getenv("TELEGRAM_API_ID") or 0)
API_HASH = os.getenv("TELEGRAM_API_HASH") or ""
STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION") or ""

SOURCE_CHAT_ID = -1001905652210
SOURCE_TOPIC_ID = 7

def extract_year(text: str):
    if not text:
        return None
    # 1. Año explícito
    m = re.search(r'(?i)\b(?:a[ñn]o|year|estreno)[:\s]+(\d{4})\b', text)
    if m:
        y = int(m.group(1))
        if 1888 <= y <= 2030:
            return y
    # 2. Quitar resoluciones
    c = re.sub(r'(?i)\b(?:1080p?|720p?|2160p?|480p?|576p?|x264|x265|h264|h265)\b', ' ', text)
    # 3. Paréntesis
    m = re.search(r'[\(\[]\s*(1[89]\d{2}|20\d{2})\s*[\)\]]', c)
    if m:
        y = int(m.group(1))
        if 1888 <= y <= 2030:
            return y
    # 4. Delimitadores
    m = re.search(r'(?:[._\-\s])(1[89]\d{2}|20\d{2})(?:[._\-\s]|$)', c)
    if m:
        y = int(m.group(1))
        if 1888 <= y <= 2030:
            return y
    return None

async def main():
    async with TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH) as client:
        chat = await client.get_entity(SOURCE_CHAT_ID)
        print(f"=== Escaneando 1000 mensajes recientes en {chat.title} (Tema {SOURCE_TOPIC_ID}) ===")

        count = 0
        clasicas = []
        rar_files = 0
        videos = 0

        async for msg in client.iter_messages(chat, reply_to=SOURCE_TOPIC_ID, limit=1000):
            count += 1
            fname = ""
            if getattr(msg, "file", None) and getattr(msg.file, "name", None):
                fname = msg.file.name or ""
            if not fname and isinstance(msg.media, MessageMediaDocument) and msg.media.document:
                for attr in msg.media.document.attributes:
                    if isinstance(attr, DocumentAttributeFilename):
                        fname = attr.file_name or ""
                        break

            fname_lower = fname.lower()
            if fname_lower.endswith((".rar", ".zip", ".7z", ".part01.rar", ".part1.rar")):
                rar_files += 1
                continue

            is_video = False
            if getattr(msg, "video", None) or fname_lower.endswith((".mkv", ".mp4", ".avi")):
                is_video = True
            elif isinstance(msg.media, MessageMediaDocument) and msg.media.document:
                if msg.media.document.mime_type and msg.media.document.mime_type.startswith("video/"):
                    is_video = True

            if not is_video:
                continue

            videos += 1
            combined = f"{fname} {msg.text or ''}"
            y = extract_year(combined)
            if y and y < 1955:
                clasicas.append((msg.id, fname, y, (msg.text or "")[:50]))

        print(f"\n--- RESUMEN TRAS ESCANEAR {count} MENSAJES ---")
        print(f"Total videos individuales: {videos}")
        print(f"Partes RAR/comprimidos ignorados: {rar_files}")
        print(f"Películas clásicas (< 1955) encontradas: {len(clasicas)}")
        for mid, fn, yr, tx in clasicas:
            print(f"  🎬 [{yr}] ID {mid} | {fn} | {tx}")

if __name__ == "__main__":
    asyncio.run(main())
