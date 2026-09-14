import asyncio
import os
import json
import random
import re
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import (
    GetForumTopicsRequest,
    CreateForumTopicRequest,
    DeleteTopicHistoryRequest,
    EditForumTopicRequest
)
from telethon.tl.types import MessageMediaDocument, DocumentAttributeFilename, DocumentAttributeVideo

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION = os.environ["TELEGRAM_STRING_SESSION"]
TARGET_CHAT = int(os.environ.get("TARGET_CHAT", "-1002097175258"))
STATE_FILE = "sync_state.json"


def is_video_or_file(msg):
    if not msg or not msg.media:
        return False
    if getattr(msg, "video", None):
        return True
    if isinstance(msg.media, MessageMediaDocument) and msg.media.document:
        doc = msg.media.document
        if doc.mime_type and doc.mime_type.startswith("video/"):
            return True
        for attr in doc.attributes:
            if isinstance(attr, (DocumentAttributeVideo,)):
                return True
            if isinstance(attr, DocumentAttributeFilename):
                fname = (attr.file_name or "").lower()
                if fname.endswith((".mkv", ".mp4", ".avi", ".mov", ".ts")):
                    return True
    return False


async def main():
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        chat = await client.get_entity(TARGET_CHAT)
        print("=" * 65)
        print(f"REPARACIÓN Y CONSOLIDACIÓN DE 'TIERRA AMARGA' EN: {chat.title} ({chat.id})")
        print("=" * 65)

        # Cargar estado
        state = {}
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
        cached_topics = state.setdefault("series_topics_cache", {})

        # Listar temas existentes en el chat
        print("Listando temas del foro...")
        all_topics = []
        offset_date = None
        offset_id = 0
        offset_topic = 0
        while True:
            res = await client(GetForumTopicsRequest(
                peer=chat,
                offset_date=offset_date,
                offset_id=offset_id,
                offset_topic=offset_topic,
                limit=100
            ))
            topics = getattr(res, "topics", [])
            if not topics:
                break
            all_topics.extend(topics)
            last = topics[-1]
            offset_topic = getattr(last, "id", 0)
            offset_id = getattr(last, "top_message", 0)
            offset_date = getattr(last, "date", None)
            if len(topics) < 100:
                break

        print(f"Total de temas encontrados en el foro: {len(all_topics)}")

        # Buscar si ya existe un tema oficial "Tierra Amarga" (excluyendo los que tienen sufijos o números de capítulo)
        tierra_main_id = None
        for t in all_topics:
            t_title = t.title.strip().lower()
            if t_title == "tierra amarga":
                tierra_main_id = t.id
                print(f"✅ Encontrado tema oficial existente 'Tierra Amarga' (ID {tierra_main_id})")
                break

        # Si no existe, crearlo
        if not tierra_main_id:
            print("Creando tema oficial 'Tierra Amarga'...")
            try:
                rand_id = random.randint(1, 2**63 - 1)
                created = await client(CreateForumTopicRequest(
                    peer=chat,
                    title="Tierra Amarga",
                    random_id=rand_id
                ))
                for update in getattr(created, "updates", []):
                    msg = getattr(update, "message", None)
                    if msg and hasattr(msg, "id"):
                        action = getattr(msg, "action", None)
                        if action and "TopicCreate" in type(action).__name__:
                            tierra_main_id = msg.id
                            break
                        elif tierra_main_id is None:
                            tierra_main_id = msg.id
                    elif hasattr(update, "id"):
                        tierra_main_id = update.id
            except Exception as e:
                print(f"Error creando tema: {e}")

        if not tierra_main_id:
            # Reintentar obtener temas por si se creó pero la respuesta no vino en updates
            res = await client(GetForumTopicsRequest(peer=chat, offset_date=None, offset_id=0, offset_topic=0, limit=20))
            for t in getattr(res, "topics", []):
                if t.title.strip().lower() == "tierra amarga":
                    tierra_main_id = t.id
                    break

        if not tierra_main_id:
            raise RuntimeError("No se pudo crear ni encontrar el tema 'Tierra Amarga'")

        print(f"🎯 Tema oficial de destino para 'Tierra Amarga': ID {tierra_main_id}")

        # Identificar temas dispersos a consolidar
        KNOWN_STRAY_IDS = {9773, 9782, 9784, 9786, 9792, 9794, 9796, 9801}
        stray_topics = []

        for t in all_topics:
            tid = t.id
            if tid == tierra_main_id:
                continue
            title = t.title.strip()
            title_lower = title.lower()

            is_stray = False
            if tid in KNOWN_STRAY_IDS:
                is_stray = True
            elif "emitido en tv" in title_lower:
                is_stray = True
            elif re.match(r"(?i)^cap[iíãÃ\ufffd\xad\s]*tulo\s*\d+", title):
                is_stray = True
            elif "tierra amarga" in title_lower and tid != tierra_main_id:
                is_stray = True

            if is_stray:
                stray_topics.append((tid, title))

        # Ordenar temas por ID ascendente para preservar el orden cronológico de emisión
        stray_topics = sorted(stray_topics, key=lambda x: x[0])
        print(f"\nTemas dispersos detectados para consolidar ({len(stray_topics)}):")
        for tid, title in stray_topics:
            print(f"  - [{tid}] '{title}'")

        # Transferir mensajes de cada tema al tema oficial
        total_transferred = 0
        for idx, (tid, title) in enumerate(stray_topics, 1):
            print(f"\n[{idx}/{len(stray_topics)}] Extrayendo archivos del tema ID {tid} ('{title}')...")
            msgs = []
            async for m in client.iter_messages(chat, reply_to=tid, reverse=True):
                if is_video_or_file(m):
                    msgs.append(m)

            print(f"  Episodios encontrados: {len(msgs)}")
            for m in msgs:
                caption = m.text or (m.file.name if m.file else "Tierra Amarga")
                fname = m.file.name if (m.file and m.file.name) else m.id
                print(f"    -> Transfiriendo a 'Tierra Amarga': {fname}")
                await client.send_message(
                    chat,
                    message=caption,
                    file=m.media,
                    reply_to=tierra_main_id
                )
                total_transferred += 1
                await asyncio.sleep(1.2)

            # Eliminar tema huérfano
            try:
                print(f"  🗑️ Eliminando tema huérfano ID {tid} ('{title}')...")
                await client(DeleteTopicHistoryRequest(peer=chat, top_msg_id=tid))
                print(f"  ✅ Tema {tid} eliminado con éxito.")
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"  ⚠️ Error o aviso eliminando tema {tid}: {e}")

        print(f"\n✅ Total de {total_transferred} episodios consolidados en 'Tierra Amarga'.")

        # Limpiar entradas de la caché
        keys_to_del = []
        for k in cached_topics:
            k_low = k.lower()
            if "tierra amarga" in k_low or "emitido en tv" in k_low or re.match(r"(?i)^cap[iíãÃ\ufffd\xad\s]*tulo", k):
                keys_to_del.append(k)

        for k in keys_to_del:
            del cached_topics[k]

        cached_topics["tierra amarga"] = tierra_main_id
        state["series_topics_cache"] = cached_topics
        if state.get("current_series_title") and ("tierra" in state["current_series_title"].lower() or "cap" in state["current_series_title"].lower() or "emitido" in state["current_series_title"].lower()):
            state["current_series_title"] = "Tierra Amarga"
            state["current_topic_id"] = tierra_main_id

        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        print("✅ sync_state.json actualizado con éxito.")
        print("\n" + "=" * 65)
        print("REPARACIÓN DE TIERRA AMARGA COMPLETADA CON ÉXITO")
        print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
