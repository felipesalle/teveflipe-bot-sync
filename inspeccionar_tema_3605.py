import asyncio
import os
import sys
import re
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetForumTopicsRequest, GetForumTopicsByIDRequest

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")

TARGET_CHAT = -1004331019870
TARGET_TOPIC_ID = 3605

async def main():
    if not SESSION_PROD:
        print("❌ SESSION_PROD no configurada.")
        return

    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client:
        print(f"🔍 Conectado con SESSION_PROD.")
        entity = await client.get_entity(TARGET_CHAT)
        print(f"📡 Canal / Supergrupo: '{entity.title}' (ID: {entity.id})")

        # 1. Inspeccionar el mensaje / topic 3605
        print(f"\n==========================================")
        print(f"1. INSPECCIONANDO TOPIC / MSG ID: {TARGET_TOPIC_ID}")
        print(f"==========================================")
        
        topic_title = "Desconocido"
        try:
            res_topic = await client(GetForumTopicsByIDRequest(peer=entity, topics=[TARGET_TOPIC_ID]))
            if res_topic.topics:
                t = res_topic.topics[0]
                topic_title = t.title
                print(f"📌 TÍTULO DEL TEMA {TARGET_TOPIC_ID}: '{t.title}'")
                print(f"   Creado por ID: {t.from_id}")
                print(f"   Top message: {t.top_message}, Mensajes leídos: {t.read_inbox_max_id}")
            else:
                print(f"⚠️ GetForumTopicsByIDRequest no devolvió el topic {TARGET_TOPIC_ID}")
        except Exception as e:
            print(f"⚠️ Error al consultar GetForumTopicsByIDRequest: {e}")

        try:
            root_msg = await client.get_messages(entity, ids=TARGET_TOPIC_ID)
            if root_msg:
                print(f"📩 Mensaje raíz {TARGET_TOPIC_ID}:")
                print(f"   Texto: {root_msg.text}")
                print(f"   Fecha: {root_msg.date}")
                if root_msg.file:
                    print(f"   Archivo adjunto: {getattr(root_msg.file, 'name', 'Sin nombre')} ({root_msg.file.size} bytes)")
                if getattr(root_msg, 'action', None):
                    print(f"   Acción: {root_msg.action}")
            else:
                print(f"⚠️ Mensaje raíz {TARGET_TOPIC_ID} no encontrado o nulo.")
        except Exception as e:
            print(f"⚠️ Error al obtener mensaje raíz: {e}")

        print(f"\n📂 Mensajes dentro del topic {TARGET_TOPIC_ID}:")
        msg_count = 0
        topic_files = []
        async for m in client.iter_messages(entity, reply_to=TARGET_TOPIC_ID, limit=100):
            msg_count += 1
            fn = getattr(m.file, 'name', '') if m.file else ''
            if fn:
                topic_files.append((m.id, fn, m.date))
            if msg_count <= 10:
                print(f"   [Msg {m.id}] {m.date} | File: '{fn}' | Texto: {m.text[:60] if m.text else ''}")

        print(f"Total mensajes en topic {TARGET_TOPIC_ID}: {msg_count}")
        print(f"Total archivos en topic: {len(topic_files)}")

        # 2. Recuperar todos los temas del canal
        print(f"\n==========================================")
        print(f"2. RECUPERANDO TEMAS DEL CANAL")
        print(f"==========================================")
        
        offset_date = None
        offset_id = 0
        offset_topic = 0
        all_topics = []

        while len(all_topics) < 500:
            try:
                res = await client(GetForumTopicsRequest(
                    peer=entity,
                    offset_date=offset_date,
                    offset_id=offset_id,
                    offset_topic=offset_topic,
                    limit=100
                ))
                if not res.topics:
                    break
                all_topics.extend(res.topics)
                if len(res.topics) < 100:
                    break
                last = res.topics[-1]
                offset_topic = last.id
                offset_id = last.top_message
                offset_date = last.date
                await asyncio.sleep(0.3)
            except Exception as e:
                print(f"Error recuperando temas: {e}")
                break

        print(f"Total temas recuperados en el canal: {len(all_topics)}")

        # 3. Analizar temas relacionados con la serie del topic 3605
        serie_keywords = [w for w in re.split(r'[^a-zA-Z0-9]', topic_title) if len(w) >= 3]
        print(f"\nBuscando temas relacionados con '{topic_title}' (Keywords: {serie_keywords}):")
        
        matches = []
        for t in all_topics:
            t_low = t.title.lower()
            if any(k.lower() in t_low for k in serie_keywords):
                matches.append(t)
                print(f"   -> Topic ID {t.id} (top_msg={t.top_message}): \"{t.title}\"")

        # 4. Detectar temas sospechosos (capítulos sueltos creados como temas)
        print(f"\n==========================================")
        print(f"3. TEMAS SOSPECHOSOS (CAPÍTULOS SUELTOS)")
        print(f"==========================================")
        suspicious = []
        for t in all_topics:
            title = t.title.strip()
            is_susp = False
            reason = ""
            if re.search(r'(?i)\b(?:s\d{1,2}e\d{1,2}|\d{1,2}x\d{1,2}|cap[ií]tulo\s*\d+|episodio\s*\d+)\b', title):
                is_susp = True
                reason = "Contiene código de capítulo en el título"
            elif re.search(r'^\d{1,3}\s*[-–—.]', title):
                is_susp = True
                reason = "Empieza por número de capítulo"
            elif any(ext in title.lower() for ext in ['.mkv', '.mp4', '.avi']):
                is_susp = True
                reason = "Tiene extensión de archivo de vídeo en el título"

            if is_susp:
                suspicious.append((t.id, t.title, reason))
                print(f"   ⚠️ Topic ID {t.id}: \"{t.title}\" -> Motivo: {reason}")

        print(f"\nTotal temas sospechosos detectados: {len(suspicious)}")

        # 5. Los 25 temas más recientes del canal
        print(f"\n==========================================")
        print(f"4. LOS 25 TEMAS MÁS RECIENTES EN EL CANAL")
        print(f"==========================================")
        sorted_recent = sorted(all_topics, key=lambda x: x.id, reverse=True)
        for t in sorted_recent[:25]:
            print(f"   Topic ID {t.id:5d} | Top Msg: {t.top_message:6d} | \"{t.title}\"")

if __name__ == "__main__":
    asyncio.run(main())
