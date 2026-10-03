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
SESSION_BUNKER = os.getenv("SESSION_BUNKER") or ""
SESSION_PROD = os.getenv("SESSION_PROD") or ""

BUNKER_SERIES_TV = -1002097175258
PROD_SERIES_TV = -1004331019870

sys.stdout.reconfigure(encoding='utf-8')

async def main():
    cb = TelegramClient(StringSession(SESSION_BUNKER), API_ID, API_HASH)
    cp = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)
    await cb.start()
    await cp.start()
    
    me_b = await cb.get_me()
    me_p = await cp.get_me()
    
    # 1. Comprobar si hay mensajes pendientes en el DM entre las dos cuentas
    print("📬 Verificando DM entre Cuenta Búnker y Cuenta Producción...")
    dm_msgs_p = [m async for m in cp.iter_messages(me_b.id, limit=50)]
    dm_msgs_b = [m async for m in cb.iter_messages(me_p.id, limit=50)]
    print(f"Mensajes residuales en DM (lado Prod): {len(dm_msgs_p)}")
    print(f"Mensajes residuales en DM (lado Búnker): {len(dm_msgs_b)}")
    
    ent_prod = await cp.get_input_entity(PROD_SERIES_TV)
    
    # Obtener temas de Producción
    print("\n📡 Obteniendo lista de temas de Producción...")
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

    print(f"Temas en Producción: {len(topics)}")

    # 2. Auditar anomalías / intrusos en todos los temas de producción
    print("\n🔍 Escaneando mensajes en Producción para detectar episodios intrusos...")
    intrusos = []
    
    # Normalizar palabras clave de cada serie
    def normalize_str(s):
        s = s.lower()
        s = re.sub(r'[\(\)\[\]\-_:,\.\?]', ' ', s)
        return set([w for w in s.split() if len(w) > 3 and w not in ["temporada", "season", "serie", "completa", "capitulo", "episodio"]])

    # Muestrear / auditar mensajes por tema
    for tid, ttitle in topics.items():
        if tid == 1:
            continue
        t_keywords = normalize_str(ttitle)
        msgs = [m async for m in cp.iter_messages(ent_prod, reply_to=tid) if not m.action and (m.file or m.text)]
        for m in msgs:
            fname = m.file.name if m.file and m.file.name else ""
            txt = m.message or ""
            content = f"{fname} {txt}"
            # Comprobar si menciona claramente otra serie muy distinta
            # Por ejemplo 'Orphan Black' en un tema que no es Orphan Black
            if "orphan black" in content.lower() and "orphan" not in ttitle.lower():
                intrusos.append({
                    "topic_id": tid,
                    "topic_title": ttitle,
                    "msg_id": m.id,
                    "file_name": fname,
                    "motivo": "Contiene 'Orphan Black' fuera de su tema"
                })

    print(f"\n🚨 Total de intrusos de Orphan Black detectados: {len(intrusos)}")
    for it in intrusos:
        print(f"   [Tema {it['topic_id']} - {it['topic_title']}] Msg ID {it['msg_id']}: {it['file_name']}")

    # 3. Comprobar dónde está Orphan Black en Búnker
    print("\n🔎 Buscando Orphan Black en el Búnker...")
    ent_bunker = await cb.get_input_entity(BUNKER_SERIES_TV)
    b_topics = {}
    offset_date = offset_id = offset_topic = 0
    while True:
        res = await cb(GetForumTopicsRequest(
            peer=ent_bunker, offset_date=offset_date, offset_id=offset_id, offset_topic=offset_topic, limit=100
        ))
        if not res.topics:
            break
        for t in res.topics:
            b_topics[t.id] = t.title
        if len(res.topics) < 100:
            break
        last = res.topics[-1]
        offset_date = last.date
        offset_id = last.top_message
        offset_topic = last.id

    for b_tid, b_title in b_topics.items():
        if "orphan" in b_title.lower():
            b_cnt = len([m async for m in cb.iter_messages(ent_bunker, reply_to=b_tid) if not m.action])
            print(f"   Búnker Tema {b_tid} ('{b_title}'): {b_cnt} mensajes.")

    await cb.disconnect()
    await cp.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
