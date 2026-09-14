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
        print(f"REPARACIÓN Y CONSOLIDACIÓN DE BONES Y LUNA EN: {chat.title} ({chat.id})")
        print("=" * 65)

        # Cargar estado
        state = {}
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
        cached_topics = state.setdefault("series_topics_cache", {})

        # -------------------------------------------------------------
        # 1. CONSOLIDAR LUNA, EL MISTERIO DE CALENDA
        # -------------------------------------------------------------
        print("\n--- 1. CONSOLIDANDO LUNA, EL MISTERIO DE CALENDA ---")
        TOPIC_LUNA_MAIN = 10002   # Luna: El Misterio De Calenda (Temporada 1)
        TOPIC_LUNA_S2 = 10016     # Luna El Misterio De Calenda (Temporada 2)

        # Intentar renombrar el tema principal a nombre limpio
        try:
            print(f"Renombrando tema {TOPIC_LUNA_MAIN} a 'Luna, El Misterio De Calenda'...")
            await client(EditForumTopicRequest(peer=chat, topic_id=TOPIC_LUNA_MAIN, title="Luna, El Misterio De Calenda"))
            print("✅ Nombre de tema actualizado correctamente.")
        except Exception as e:
            print(f"Aviso actualizando título de Luna ({TOPIC_LUNA_MAIN}): {e}")

        # Transferir episodios de Temporada 2 a Temporada 1 / Tema Principal
        luna_s2_msgs = []
        async for m in client.iter_messages(chat, reply_to=TOPIC_LUNA_S2, reverse=True):
            if is_video_or_file(m):
                luna_s2_msgs.append(m)

        print(f"Episodios encontrados en Temporada 2 (Topic {TOPIC_LUNA_S2}): {len(luna_s2_msgs)}")
        for m in luna_s2_msgs:
            caption = m.text or (m.file.name if m.file else "Luna T2")
            print(f"-> Moviendo a tema principal de Luna: {m.file.name if m.file else m.id}")
            await client.send_message(
                chat,
                message=caption,
                file=m.media,
                reply_to=TOPIC_LUNA_MAIN
            )
            await asyncio.sleep(1.2)

        # Eliminar el tema duplicado de Temporada 2
        try:
            print(f"🗑️ Eliminando tema duplicado Temporada 2 (ID {TOPIC_LUNA_S2})...")
            await client(DeleteTopicHistoryRequest(peer=chat, top_msg_id=TOPIC_LUNA_S2))
            print("✅ Tema duplicado de Luna eliminado con éxito.")
        except Exception as e:
            print(f"Aviso eliminando {TOPIC_LUNA_S2}: {e}")

        # Actualizar caché de Luna
        cached_topics.pop("luna el misterio de calenda", None)
        cached_topics["luna, el misterio de calenda"] = TOPIC_LUNA_MAIN
        cached_topics["luna: el misterio de calenda"] = TOPIC_LUNA_MAIN
        cached_topics["luna: el misterio de calenda ✓"] = TOPIC_LUNA_MAIN
        cached_topics["luna"] = TOPIC_LUNA_MAIN
        print("✅ Luna consolidada en un único tema.")

        # -------------------------------------------------------------
        # 2. CONSOLIDAR TODOS LOS TEMAS DE BONES
        # -------------------------------------------------------------
        print("\n--- 2. CONSOLIDANDO SERIE BONES ---")
        # Encontrar todos los temas de Bones registrados en caché o con 'bones' en el nombre
        bones_items = [(k, v) for k, v in cached_topics.items() if "bones" in k.lower()]
        # Ordenar por ID de tema (mantiene el orden cronológico de emisión T1 a T6)
        bones_items = sorted(bones_items, key=lambda x: x[1])
        unique_bones_topic_ids = []
        for _, tid in bones_items:
            if tid not in unique_bones_topic_ids:
                unique_bones_topic_ids.append(tid)

        print(f"Total de temas individuales de Bones encontrados: {len(unique_bones_topic_ids)}")

        if unique_bones_topic_ids:
            # Crear el tema único oficial "Bones"
            print("Creando tema oficial 'Bones'...")
            bones_main_id = None
            try:
                created = await client(CreateForumTopicRequest(
                    peer=chat,
                    title="Bones",
                    random_id=random.randint(1, 2**63 - 1)
                ))
                for update in getattr(created, "updates", []):
                    msg = getattr(update, "message", None)
                    if msg and hasattr(msg, "id"):
                        action = getattr(msg, "action", None)
                        if action and "TopicCreate" in type(action).__name__:
                            bones_main_id = msg.id
                            break
                        elif bones_main_id is None:
                            bones_main_id = msg.id
                    elif hasattr(update, "id"):
                        bones_main_id = update.id
            except Exception as e:
                print(f"Error creando tema Bones: {e}")

            if not bones_main_id:
                # Buscar tema existente con título Bones
                res = await client(GetForumTopicsRequest(peer=chat, offset_date=None, offset_id=0, offset_topic=0, limit=20))
                for t in res.topics:
                    if t.title.strip().lower() == "bones":
                        bones_main_id = t.id
                        break

            print(f"✅ Tema oficial 'Bones' creado/identificado con ID: {bones_main_id}")

            # Recorrer cada uno de los 131 temas individuales y transferir sus episodios a Bones
            episodes_moved = 0
            for idx, tid in enumerate(unique_bones_topic_ids, 1):
                if tid == bones_main_id:
                    continue
                print(f"[{idx}/{len(unique_bones_topic_ids)}] Extrayendo archivos del tema ID {tid}...")
                msgs_in_topic = []
                async for m in client.iter_messages(chat, reply_to=tid, reverse=True):
                    if is_video_or_file(m):
                        msgs_in_topic.append(m)

                for m in msgs_in_topic:
                    caption = m.text or (m.file.name if m.file else "Bones")
                    print(f"  -> Transfiriendo a Bones: {m.file.name if m.file else m.id}")
                    await client.send_message(
                        chat,
                        message=caption,
                        file=m.media,
                        reply_to=bones_main_id
                    )
                    episodes_moved += 1
                    await asyncio.sleep(1.0)

                # Eliminar el tema individual
                try:
                    await client(DeleteTopicHistoryRequest(peer=chat, top_msg_id=tid))
                    await asyncio.sleep(0.3)
                except Exception as e:
                    print(f"  Aviso eliminando tema {tid}: {e}")

            print(f"✅ Total de {episodes_moved} episodios transferidos al tema único 'Bones'.")

            # Limpiar entradas de bones del caché
            keys_to_del = [k for k in cached_topics if "bones" in k.lower()]
            for k in keys_to_del:
                del cached_topics[k]

            cached_topics["bones"] = bones_main_id
            print("✅ Caché de Bones unificado en 'bones'.")

        # Guardar sync_state.json
        state["series_topics_cache"] = cached_topics
        if state.get("current_series_title") and "bones" in state.get("current_series_title", "").lower():
            state["current_series_title"] = "Bones"
            state["current_topic_id"] = cached_topics.get("bones")

        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        print("✅ sync_state.json actualizado con éxito.")

        print("\n" + "=" * 65)
        print("REPARACIÓN COMPLETADA CON ÉXITO")
        print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
