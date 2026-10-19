import asyncio
import os
import sys
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")
TARGET_CHAT = -1004331019870

async def main():
    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client:
        print("🔍 Conectado con SESSION_PROD.")
        entity = await client.get_entity(TARGET_CHAT)
        
        # Obtener los mensajes del 3600 al 3650
        msg_ids = list(range(3600, 3650))
        msgs = await client.get_messages(entity, ids=msg_ids)
        
        print("\n=== MENSAJES 3600 A 3650 EN PROD_SERIES ===")
        for m in msgs:
            if not m:
                continue
            fn = getattr(m.file, 'name', '') if m.file else ''
            reply = m.reply_to
            top_id = getattr(reply, 'reply_to_top_id', None) or getattr(reply, 'reply_to_msg_id', None)
            is_forum_topic = getattr(m, 'action', None)
            print(f"ID: {m.id:5d} | Date: {m.date} | TopID/Reply: {top_id} | Action: {is_forum_topic} | File: '{fn}' | Text: '{m.text}'")

        # Ahora veamos los mensajes 7490 a 7510 (los últimos que vimos en Angie Tribeca)
        msg_ids_recent = list(range(7490, 7510))
        msgs_recent = await client.get_messages(entity, ids=msg_ids_recent)
        print("\n=== MENSAJES 7490 A 7510 EN PROD_SERIES ===")
        for m in msgs_recent:
            if not m:
                continue
            fn = getattr(m.file, 'name', '') if m.file else ''
            reply = m.reply_to
            top_id = getattr(reply, 'reply_to_top_id', None) or getattr(reply, 'reply_to_msg_id', None)
            is_forum_topic = getattr(m, 'action', None)
            print(f"ID: {m.id:5d} | Date: {m.date} | TopID/Reply: {top_id} | Action: {is_forum_topic} | File: '{fn}' | Text: '{m.text}'")

if __name__ == "__main__":
    asyncio.run(main())
