import asyncio
import os
import re
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetForumTopicsRequest

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")

BUNKER_SERIES = -1002097175258
PROD_SERIES = -1004331019870

async def main():
    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client:
        print("=== CONECTADO CON SESSION_PROD ===")
        
        # 1. Verificar acceso a los diálogos
        print("Listando canales a los que tiene acceso esta sesión...")
        accessible_chats = []
        async for dialog in client.iter_dialogs():
            if dialog.is_channel or dialog.is_group:
                accessible_chats.append((dialog.id, dialog.title))
                if "bunker" in dialog.title.lower() or "repositorio" in dialog.title.lower() or "series" in dialog.title.lower():
                    print(f"  * Chat: {dialog.title} (ID: {dialog.id})")

        # 2. Buscar True Blood en Búnker Series si tenemos acceso
        bunker_found = False
        for cid, title in accessible_chats:
            if cid == BUNKER_SERIES or "series tv" in title.lower() and "bunker" in title.lower():
                bunker_found = True
                print(f"\nBuscando 'True Blood' en {title} ({cid})...")
                entity = await client.get_entity(cid)
                
                # Buscar en topics
                offset_date = None
                offset_id = 0
                offset_topic = 0
                while True:
                    res = await client(GetForumTopicsRequest(peer=entity, offset_date=offset_date, offset_id=offset_id, offset_topic=offset_topic, limit=100))
                    if not res.topics:
                        break
                    for t in res.topics:
                        if "true blood" in t.title.lower() or "sangre fresca" in t.title.lower():
                            print(f"🎯 ¡TEMA ENCONTRADO EN BÚNKER! Topic {t.id}: '{t.title}' (top_msg={t.top_message})")
                    if len(res.topics) < 100:
                        break
                    last = res.topics[-1]
                    offset_topic = last.id
                    offset_id = last.top_message
                    offset_date = last.date

        # 3. Búsqueda global de mensajes con True Blood en todos los chats accesibles
        print("\nBúsqueda global de mensajes 'True Blood'...")
        async for m in client.iter_messages(None, search="True Blood", limit=20):
            chat_name = getattr(m.chat, 'title', str(m.chat_id))
            fn = m.file.name if m.file else ""
            print(f"- En '{chat_name}' (ID {m.chat_id}) | Msg {m.id} | Topic {m.reply_to_msg_id} | Archivo: {fn}")

if __name__ == "__main__":
    asyncio.run(main())
