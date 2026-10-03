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

# Lista de palabras clave por serie para comprobar si algún archivo pertenece a otra serie
SERIES_SIGNATURES = [
    ("orphan black", r"orphan\s*black"),
    ("cobra kai", r"cobra\s*kai"),
    ("better call saul", r"better\s*call\s*saul"),
    ("the blacklist", r"the\s*blacklist|blacklist"),
    ("eric", r"eric"),
    ("chicago fire", r"chicago\s*fire"),
    ("chicago justice", r"chicago\s*justice"),
    ("atlanta", r"atlanta"),
    ("castle", r"castle"),
    ("outlander", r"outlander"),
    ("archer", r"archer"),
    ("dexter", r"dexter"),
    ("suits", r"suits"),
    ("friends", r"friends"),
    ("los simpsons", r"los\s*simpson|simpsons"),
    ("futurama", r"futurama"),
    ("the boys", r"the\s*boys"),
    ("shogun", r"shogun"),
    ("juego de tronos", r"juego\s*de\s*tronos|game\s*of\s*thrones"),
    ("los soprano", r"los\s*soprano|sopranos"),
    ("cosas de casa", r"cosas\s*de\s*casa"),
    ("bones", r"bones"),
    ("la casa del dragon", r"casa\s*del\s*drag"),
]

async def main():
    cp = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)
    await cp.start()
    
    ent_prod = await cp.get_input_entity(PROD_SERIES_TV)
    
    # 1. Obtener temas
    topics = {}
    offset_date = offset_id = offset_topic = 0
    while True:
        res = await cp(GetForumTopicsRequest(
            peer=ent_prod, offset_date=offset_date, offset_id=offset_id, offset_topic=offset_topic, limit=100
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

    print(f"📡 {len(topics)} temas en Producción.")

    # 2. Iterar todos los temas y comprobar si algún archivo menciona otra serie
    discrepancias = []
    
    for tid, ttitle in topics.items():
        if tid == 1:
            continue
        t_lower = ttitle.lower()
        
        async for m in cp.iter_messages(ent_prod, reply_to=tid):
            if m.action:
                continue
            fname = (m.file.name if m.file and m.file.name else "")
            txt = m.message or ""
            full = f"{fname} {txt}".lower()
            if not full.strip():
                continue
                
            for sname, spattern in SERIES_SIGNATURES:
                if re.search(spattern, full):
                    # Coincide con la firma de una serie distinta
                    if sname not in t_lower and not re.search(spattern, t_lower):
                        discrepancias.append({
                            "current_topic_id": tid,
                            "current_topic_title": ttitle,
                            "detected_series": sname,
                            "msg_id": m.id,
                            "file_name": fname
                        })

    print(f"\n🔍 Total discrepancias encontradas: {len(discrepancias)}")
    for d in discrepancias:
        print(f"❌ [Tema '{d['current_topic_title']}' ID {d['current_topic_id']}] -> Detectado archivo de '{d['detected_series']}': Msg {d['msg_id']} ({d['file_name']})")

    await cp.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
