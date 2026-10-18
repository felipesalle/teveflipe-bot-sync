import asyncio
import os
import re
from collections import defaultdict
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")

PROD_SERIES = -1004331019870
TOPIC_ID = 8414

def clean_series_name(file_name, text):
    name = file_name or text or "Desconocido"
    # Quitar extension
    name = re.sub(r'\.(mkv|mp4|avi)$', '', name, flags=re.I)
    
    # Patrones para quitar season/episode: S01E01, 1x01, _S01E01_, etc.
    s = re.split(r'(?i)[_\s\.\-]*(?:s\d{1,2}|temporada|\d{1,2}x\d{1,2}|cap[íi]tulo|\d{1,2}\.\d{1,2})', name)[0]
    s = s.strip(" .-_")
    if not s or s.isdigit():
        # Quizas el formato es "1x01 - The Young Pope"
        m = re.search(r'(?i)\d{1,2}x\d{1,2}\s*[-_–]\s*(.+)', name)
        if m:
            s = m.group(1).strip()
        else:
            s = name
    return s.strip()

async def main():
    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client:
        prod_entity = await client.get_entity(PROD_SERIES)

        root_msg = await client.get_messages(prod_entity, ids=TOPIC_ID)
        topic_title = "Topic 8414"
        if root_msg and root_msg.action and hasattr(root_msg.action, 'title'):
            topic_title = root_msg.action.title

        print(f"==================================================")
        print(f"CANAL: {prod_entity.title}")
        print(f"TEMA 8414: {topic_title}")
        print(f"==================================================")

        series_groups = defaultdict(list)
        total = 0
        async for m in client.iter_messages(prod_entity, reply_to=TOPIC_ID, reverse=True):
            total += 1
            fn = m.file.name if m.file else (m.text[:40] if m.text else "Sin nombre")
            series_title = clean_series_name(fn, m.text)
            series_groups[series_title].append({
                "msg_id": m.id,
                "file_name": fn,
                "size_mb": round(m.file.size / (1024*1024), 1) if m.file else 0
            })

        print(f"\nTOTAL MENSAJES: {total}")
        print(f"TOTAL SERIES IDENTIFICADAS: {len(series_groups)}\n")

        for series, items in sorted(series_groups.items(), key=lambda x: -len(x[1])):
            print(f"📺 {series} ({len(items)} capítulos/archivos):")
            sample_eps = [it['file_name'] for it in items[:3]]
            print(f"   Ejemplos: {', '.join(sample_eps)}")
            print(f"   IDs: del {items[0]['msg_id']} al {items[-1]['msg_id']}\n")

if __name__ == "__main__":
    asyncio.run(main())
