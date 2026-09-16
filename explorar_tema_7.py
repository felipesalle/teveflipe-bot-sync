import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetForumTopicsByIDRequest, GetForumTopicsRequest
from telethon.tl.types import MessageMediaDocument, DocumentAttributeFilename

API_ID = int(os.getenv("TELEGRAM_API_ID") or 0)
API_HASH = os.getenv("TELEGRAM_API_HASH") or ""
STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION") or ""

SOURCE_CHAT_ID = -1001905652210
SOURCE_TOPIC_ID = 7

async def main():
    async with TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH) as client:
        chat = await client.get_entity(SOURCE_CHAT_ID)
        print(f"=== CHAT ENCONTRADO: {chat.title} (ID: {chat.id}) ===")

        # Inspeccionar Tema 7
        try:
            res = await client(GetForumTopicsByIDRequest(peer=chat, topics=[SOURCE_TOPIC_ID]))
            for t in getattr(res, "topics", []):
                print(f"Tema ID: {t.id} | Título: '{t.title}' | Total mensajes: {getattr(t, 'total_messages', 'desconocido')}")
        except Exception as e:
            print(f"No se pudo consultar topic info directo: {e}")

        print("\n--- OBTENIENDO MENSAJES DE MUESTRA DEL TEMA 7 (ÚLTIMOS 20) ---")
        count = 0
        async for msg in client.iter_messages(chat, reply_to=SOURCE_TOPIC_ID, limit=20):
            count += 1
            fname = msg.file.name if getattr(msg, "file", None) and getattr(msg.file, "name", None) else ""
            if not fname and isinstance(msg.media, MessageMediaDocument) and msg.media.document:
                for attr in msg.media.document.attributes:
                    if isinstance(attr, DocumentAttributeFilename):
                        fname = attr.file_name or ""
            text_preview = (msg.text or "").replace("\n", " ")[:60]
            has_video = bool(msg.video or (msg.media and isinstance(msg.media, MessageMediaDocument)))
            print(f"[{count}] Msg ID {msg.id} | Video: {has_video} | File: {fname} | Texto: {text_preview}")

        print("\n--- OBTENIENDO MENSAJES ANTIGUOS DEL TEMA 7 (PRIMEROS 10) ---")
        count2 = 0
        async for msg in client.iter_messages(chat, reply_to=SOURCE_TOPIC_ID, limit=10, reverse=True):
            count2 += 1
            fname = msg.file.name if getattr(msg, "file", None) and getattr(msg.file, "name", None) else ""
            if not fname and isinstance(msg.media, MessageMediaDocument) and msg.media.document:
                for attr in msg.media.document.attributes:
                    if isinstance(attr, DocumentAttributeFilename):
                        fname = attr.file_name or ""
            text_preview = (msg.text or "").replace("\n", " ")[:60]
            print(f"[{count2}] Msg ID {msg.id} | File: {fname} | Texto: {text_preview}")

if __name__ == "__main__":
    asyncio.run(main())
