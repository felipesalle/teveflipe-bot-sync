import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaDocument, DocumentAttributeFilename

API_ID = int(os.getenv("TELEGRAM_API_ID") or 0)
API_HASH = os.getenv("TELEGRAM_API_HASH") or ""
STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION") or ""

SOURCE_CHAT_ID = -1001905652210
SOURCE_TOPIC_ID = 7

async def main():
    async with TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH) as client:
        chat = await client.get_entity(SOURCE_CHAT_ID)
        print(f"=== Probando búsqueda por año en {chat.title} (Tema {SOURCE_TOPIC_ID}) ===")

        for test_year in ["1942", "1939", "1954", "1931", "1927"]:
            print(f"\nBuscando '{test_year}' en Tema 7...")
            count = 0
            async for msg in client.iter_messages(chat, search=test_year, reply_to=SOURCE_TOPIC_ID, limit=5):
                count += 1
                fname = msg.file.name if getattr(msg, "file", None) and getattr(msg.file, "name", None) else ""
                if not fname and isinstance(msg.media, MessageMediaDocument) and msg.media.document:
                    for attr in msg.media.document.attributes:
                        if isinstance(attr, DocumentAttributeFilename):
                            fname = attr.file_name or ""
                text_preview = (msg.text or "").replace("\n", " ")[:60]
                print(f"  -> [{count}] ID {msg.id} | File: {fname} | Texto: {text_preview}")
            print(f"  Total encontrados para '{test_year}': {count}")

if __name__ == "__main__":
    asyncio.run(main())
