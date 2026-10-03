import asyncio
import os
import sys
import re
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetForumTopicsRequest

load_dotenv("e:/TeveFlipe/sync_bunker/.env")

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD") or ""
PROD_SERIES_TV = -1004331019870

sys.stdout.reconfigure(encoding='utf-8')

async def main():
    client = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)
    await client.start()
    
    ent_prod = await client.get_input_entity(PROD_SERIES_TV)
    
    # 1. Obtener todos los temas de Producción
    print("📡 Obteniendo temas del canal Producción...")
    topics = {}
    offset_date = 0
    offset_id = 0
    offset_topic = 0
    while True:
        res = await client(GetForumTopicsRequest(
            peer=ent_prod,
            offset_date=offset_date,
            offset_id=offset_id,
            offset_topic=offset_topic,
            limit=100
        ))
        if not res.topics:
            break
        for t in res.topics:
            topics[t.id] = t.title
        if len(res.topics) < 100:
            break
        last = res.topics[-1]
        offset_date = last.date
        offset_id = last.top_message
        offset_topic = last.id

    print(f"Total de temas encontrados en Producción: {len(topics)}")
    
    # 2. Buscar específicamente 'Orphan Black' en todos los temas
    print("\n🔍 Buscando archivos/mensajes de 'Orphan Black' en todo el canal...")
    orphan_finds = []
    
    # También podemos buscar si hay temas cruzados
    all_msgs_count = 0
    async for msg in client.iter_messages(ent_prod, limit=10000):
        all_msgs_count += 1
        text = msg.message or ""
        file_name = ""
        if msg.file and msg.file.name:
            file_name = msg.file.name
            
        full_info = f"{file_name} {text}".strip()
        
        # Tema del mensaje
        tid = getattr(msg, 'reply_to_msg_id', None)
        # O en reply_to
        reply_to_top = None
        if msg.reply_to:
            reply_to_top = getattr(msg.reply_to, 'reply_to_top_id', None) or getattr(msg.reply_to, 'reply_to_msg_id', None)
        
        current_topic_id = reply_to_top or tid or 1
        current_topic_title = topics.get(current_topic_id, f"Desconocido ({current_topic_id})")
        
        if re.search(r"orphan\s*black", full_info, re.IGNORECASE):
            orphan_finds.append({
                "msg_id": msg.id,
                "topic_id": current_topic_id,
                "topic_title": current_topic_title,
                "file_name": file_name,
                "text_snippet": text[:80]
            })

    print(f"\n📊 Total mensajes analizados: {all_msgs_count}")
    print(f"🎯 Total coincidencias de 'Orphan Black': {len(orphan_finds)}")
    
    # Agrupar por tema
    by_topic = {}
    for f in orphan_finds:
        t_key = f"{f['topic_title']} (ID {f['topic_id']})"
        by_topic.setdefault(t_key, []).append(f)
        
    for t_key, items in by_topic.items():
        print(f"\n📁 En tema '{t_key}': {len(items)} archivos")
        for it in items[:5]:
            print(f"   - Msg {it['msg_id']}: {it['file_name'] or it['text_snippet']}")
        if len(items) > 5:
            print(f"   ... y {len(items)-5} más.")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
