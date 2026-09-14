import asyncio
import os
import json
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import (
    GetForumTopicsRequest,
    CreateForumTopicRequest,
    DeleteTopicHistoryRequest
)
from telethon.tl.types import MessageMediaDocument, DocumentAttributeFilename, DocumentAttributeVideo

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION = os.environ["TELEGRAM_STRING_SESSION"]
TARGET_CHAT = int(os.environ.get("TARGET_CHAT", "-1002097175258"))
STATE_FILE = "sync_state.json"

TOPIC_SUPERNATURAL_MAIN = 9506
TOPIC_SUPERNATURAL_T2 = 9530
TOPIC_SOBRENATURAL_EMPTY = 9553

TOPIC_TED_LASSO_EMPTY = 9674
TOPIC_REASONABLE_DOUBT_EMPTY = 9621

LOS_ORIGINALES_TOPIC_IDS = [
    9633, 9636, 9638, 9640, 9642, 9644, 9646, 9648, 9650, 9652,
    9654, 9656, 9658, 9660, 9662, 9664, 9666, 9668, 9670, 9672
]


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
        print("=" * 60)
        print(f"REPARACIÓN Y CONSOLIDACIÓN DE SERIES EN: {chat.title} ({chat.id})")
        print("=" * 60)

        # Cargar estado
        state = {}
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
        cached_topics = state.setdefault("series_topics_cache", {})

        # -------------------------------------------------------------
        # 1. ARREGLAR SUPERNATURAL
        # -------------------------------------------------------------
        print("\n--- 1. CONSOLIDANDO SUPERNATURAL ---")
        # Pasar episodios de Temporada 2 (9530) al tema principal (9506)
        print(f"Transfiriendo episodios de 'Segunda Temporada' (Topic {TOPIC_SUPERNATURAL_T2}) a 'Supernatural' (Topic {TOPIC_SUPERNATURAL_MAIN})...")
        t2_msgs = []
        async for m in client.iter_messages(chat, reply_to=TOPIC_SUPERNATURAL_T2, reverse=True):
            if is_video_or_file(m):
                t2_msgs.append(m)

        print(f"Total episodios encontrados en T2: {len(t2_msgs)}")
        for m in t2_msgs:
            caption = m.text or (m.file.name if m.file else "Supernatural T2")
            print(f"-> Moviendo a Supernatural: {m.file.name if m.file else m.id}")
            await client.send_message(
                chat,
                message=caption,
                file=m.media,
                reply_to=TOPIC_SUPERNATURAL_MAIN
            )
            await asyncio.sleep(1.5)

        # Eliminar el tema de Segunda Temporada
        try:
            print(f"🗑️ Eliminando tema desglosado 'Segunda Temporada' (ID {TOPIC_SUPERNATURAL_T2})...")
            await client(DeleteTopicHistoryRequest(peer=chat, top_msg_id=TOPIC_SUPERNATURAL_T2))
        except Exception as e:
            print(f"Aviso eliminando {TOPIC_SUPERNATURAL_T2}: {e}")

        # Eliminar el tema vacío Sobrenatural
        try:
            print(f"🗑️ Eliminando tema duplicado vacío 'Sobrenatural' (ID {TOPIC_SOBRENATURAL_EMPTY})...")
            await client(DeleteTopicHistoryRequest(peer=chat, top_msg_id=TOPIC_SOBRENATURAL_EMPTY))
        except Exception as e:
            print(f"Aviso eliminando {TOPIC_SOBRENATURAL_EMPTY}: {e}")

        cached_topics.pop("▶️segunda temporada", None)
        cached_topics.pop("sobrenatural", None)
        cached_topics["supernatural"] = TOPIC_SUPERNATURAL_MAIN
        print("✅ Supernatural consolidado en un único tema.")

        # -------------------------------------------------------------
        # 2. ARREGLAR LOS ORIGINALES
        # -------------------------------------------------------------
        print("\n--- 2. CONSOLIDANDO LOS ORIGINALES ---")
        # Crear un único tema para 'Los Originales'
        print("Creando tema único 'Los Originales'...")
        import random
        created_orig = await client(CreateForumTopicRequest(
            peer=chat,
            title="Los Originales",
            random_id=random.randint(1, 2**63 - 1)
        ))
        
        orig_topic_id = None
        for update in getattr(created_orig, "updates", []):
            msg = getattr(update, "message", None)
            if msg and hasattr(msg, "id"):
                action = getattr(msg, "action", None)
                if action and "TopicCreate" in type(action).__name__:
                    orig_topic_id = msg.id
                    break
                elif orig_topic_id is None:
                    orig_topic_id = msg.id
            elif hasattr(update, "id"):
                orig_topic_id = update.id

        if not orig_topic_id:
            # Si no se pudo determinar el ID, buscarlo
            topics_res = await client(GetForumTopicsRequest(peer=chat, offset_date=None, offset_id=0, offset_topic=0, limit=10))
            for t in topics_res.topics:
                if t.title.lower() == "los originales":
                    orig_topic_id = t.id
                    break

        print(f"✅ Tema único 'Los Originales' listo (ID: {orig_topic_id})")

        # Recorrer cada subtema individual, extraer los episodios y reenviarlos al tema único
        for tid in LOS_ORIGINALES_TOPIC_IDS:
            print(f"Procesando subtema individual {tid}...")
            async for m in client.iter_messages(chat, reply_to=tid, reverse=True):
                if is_video_or_file(m):
                    caption = m.text or (m.file.name if m.file else "Los Originales")
                    print(f"-> Transfiriendo a 'Los Originales': {m.file.name if m.file else m.id}")
                    await client.send_message(
                        chat,
                        message=caption,
                        file=m.media,
                        reply_to=orig_topic_id
                    )
                    await asyncio.sleep(1.5)

            # Borrar el subtema individual
            try:
                print(f"🗑️ Eliminando subtema individual ID {tid}...")
                await client(DeleteTopicHistoryRequest(peer=chat, top_msg_id=tid))
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"Aviso eliminando subtema {tid}: {e}")

            # Quitar del caché
            for k, v in list(cached_topics.items()):
                if v == tid:
                    del cached_topics[k]

        cached_topics["los originales"] = orig_topic_id
        print("✅ Todos los episodios de 'Los Originales' consolidados en un único tema.")

        # -------------------------------------------------------------
        # 3. ELIMINAR TEMAS VACÍOS (Ted Lasso, Reasonable Doubt)
        # -------------------------------------------------------------
        print("\n--- 3. LIMPIEZA DE TEMAS VACÍOS ---")
        empty_targets = [
            ("Ted Lasso", TOPIC_TED_LASSO_EMPTY),
            ("Reasonable Doubt", TOPIC_REASONABLE_DOUBT_EMPTY)
        ]

        for name, tid in empty_targets:
            # Comprobar que realmente no tiene videos
            v_count = 0
            async for m in client.iter_messages(chat, reply_to=tid, limit=10):
                if is_video_or_file(m):
                    v_count += 1

            if v_count == 0:
                try:
                    print(f"🗑️ Eliminando tema vacío '{name}' (ID {tid})...")
                    await client(DeleteTopicHistoryRequest(peer=chat, top_msg_id=tid))
                    for k, v in list(cached_topics.items()):
                        if v == tid:
                            del cached_topics[k]
                    print(f"✅ Tema vacío '{name}' eliminado.")
                except Exception as e:
                    print(f"Error eliminando tema {name} ({tid}): {e}")
            else:
                print(f"ℹ️ El tema '{name}' tiene {v_count} archivos multimedia. No se elimina.")

        # Si current_series_title era Ted Lasso, resetearlo
        if state.get("current_series_title") == "Ted Lasso":
            state["current_series_title"] = None
            state["current_topic_id"] = None

        # Guardar sync_state.json actualizado
        state["series_topics_cache"] = cached_topics
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        print("✅ sync_state.json actualizado.")

        print("\n" + "=" * 60)
        print("PROCESO DE REPARACIÓN Y LIMPIEZA FINALIZADO CON ÉXITO")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
