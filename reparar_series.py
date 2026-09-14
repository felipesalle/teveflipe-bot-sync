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
        print(f"CONSOLIDACIÓN DE 'ENTRE FANTASMAS' EN: {chat.title} ({chat.id})")
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

        # Buscar si ya existe un tema oficial "Entre Fantasmas"
        ef_main_id = None
        for t in all_topics:
            t_title = t.title.strip().lower()
            if t_title == "entre fantasmas":
                ef_main_id = t.id
                print(f"✅ Encontrado tema oficial existente 'Entre Fantasmas' (ID {ef_main_id})")
                break

        # Si no existe, crearlo
        if not ef_main_id:
            print("Creando tema oficial 'Entre Fantasmas'...")
            try:
                rand_id = random.randint(1, 2**63 - 1)
                created = await client(CreateForumTopicRequest(
                    peer=chat,
                    title="Entre Fantasmas",
                    random_id=rand_id
                ))
                for update in getattr(created, "updates", []):
                    msg = getattr(update, "message", None)
                    if msg and hasattr(msg, "id"):
                        action = getattr(msg, "action", None)
                        if action and "TopicCreate" in type(action).__name__:
                            ef_main_id = msg.id
                            break
                        elif ef_main_id is None:
                            ef_main_id = msg.id
                    elif hasattr(update, "id"):
                        ef_main_id = update.id
            except Exception as e:
                print(f"Error creando tema: {e}")

        if not ef_main_id:
            # Reintentar obtener temas
            res = await client(GetForumTopicsRequest(peer=chat, offset_date=None, offset_id=0, offset_topic=0, limit=20))
            for t in getattr(res, "topics", []):
                if t.title.strip().lower() == "entre fantasmas":
                    ef_main_id = t.id
                    break

        if not ef_main_id:
            raise RuntimeError("No se pudo crear ni encontrar el tema 'Entre Fantasmas'")

        print(f"🎯 Tema oficial de destino para 'Entre Fantasmas': ID {ef_main_id}")

        # Identificar los temas dispersos de Entre Fantasmas
        # El rango exacto generado por el sync es 11011 <= tid <= 11241
        ef_topic_ids_from_cache = {v for k, v in cached_topics.items() if 11011 <= v <= 11241}
        stray_topics = []

        for t in all_topics:
            tid = t.id
            if tid == ef_main_id:
                continue
            title = t.title.strip()

            if (11011 <= tid <= 11241) or (tid in ef_topic_ids_from_cache):
                stray_topics.append((tid, title))

        # Ordenar por ID ascendente para respetar el orden cronológico de emisión (1x01 -> 5x22)
        stray_topics = sorted(stray_topics, key=lambda x: x[0])
        print(f"\nTemas individuales de 'Entre Fantasmas' detectados para consolidar: {len(stray_topics)}")

        # Transferir mensajes de cada tema al tema oficial
        total_transferred = 0
        for idx, (tid, title) in enumerate(stray_topics, 1):
            print(f"[{idx}/{len(stray_topics)}] Extrayendo archivos del tema ID {tid} ('{title}')...")
            msgs = []
            async for m in client.iter_messages(chat, reply_to=tid, reverse=True):
                if is_video_or_file(m):
                    msgs.append(m)

            for m in msgs:
                caption = m.text or (m.file.name if m.file else f"Entre Fantasmas - {title}")
                fname = m.file.name if (m.file and m.file.name) else m.id
                print(f"  -> Transfiriendo a 'Entre Fantasmas': {fname}")
                await client.send_message(
                    chat,
                    message=caption,
                    file=m.media,
                    reply_to=ef_main_id
                )
                total_transferred += 1
                await asyncio.sleep(1.1)

            # Eliminar tema huérfano
            try:
                await client(DeleteTopicHistoryRequest(peer=chat, top_msg_id=tid))
                await asyncio.sleep(0.4)
            except Exception as e:
                print(f"  ⚠️ Aviso eliminando tema {tid}: {e}")

        print(f"\n✅ Total de {total_transferred} episodios consolidados en 'Entre Fantasmas'.")

        # Limpiar entradas de la caché de Entre Fantasmas
        keys_to_del = [k for k, v in cached_topics.items() if 11011 <= v <= 11241]
        for k in keys_to_del:
            del cached_topics[k]

        cached_topics["entre fantasmas"] = ef_main_id
        cached_topics["ghost whisperer"] = ef_main_id
        state["series_topics_cache"] = cached_topics

        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        print("✅ sync_state.json actualizado con éxito.")
        print("\n" + "=" * 65)
        print("REPARACIÓN DE ENTRE FANTASMAS COMPLETADA CON ÉXITO")
        print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
