import asyncio
import os
import random
from telethon import TelegramClient, utils
from telethon.sessions import StringSession
from telethon.tl.functions.messages import (
    ToggleNoForwardsRequest,
    CreateForumTopicRequest,
    DeleteTopicHistoryRequest,
    GetForumTopicsRequest
)
from telethon.tl.types import MessageMediaDocument, DocumentAttributeFilename, DocumentAttributeVideo

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION = os.environ["TELEGRAM_STRING_SESSION"]

SRC_SPANISH_CHAT = -1004419790119
SRC_TOPIC_MACHOS = 10882
SRC_TOPIC_BARCO = 10929

DEMO_SPANISH_CHAT = -1004379770680


def is_video(m):
    if not m or not m.media:
        return False
    if getattr(m, "video", None):
        return True
    if isinstance(m.media, MessageMediaDocument) and m.media.document:
        doc = m.media.document
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


async def recreate_topic(client, chat_entity, title):
    """Elimina temas previos con el mismo nombre para empezar limpios y crea uno nuevo."""
    try:
        res = await client(GetForumTopicsRequest(peer=chat_entity, offset_date=None, offset_id=0, offset_topic=0, limit=30))
        for t in getattr(res, "topics", []):
            if t.title.strip().lower() == title.strip().lower():
                print(f"  -> Eliminando versión previa del tema '{t.title}' (ID {t.id})...")
                try:
                    await client(DeleteTopicHistoryRequest(peer=chat_entity, top_msg_id=t.id))
                    await asyncio.sleep(0.5)
                except Exception as e:
                    print(f"     Aviso eliminando: {e}")
    except Exception:
        pass

    rand_id = random.randint(1, 2**63 - 1)
    created = await client(CreateForumTopicRequest(peer=chat_entity, title=title, random_id=rand_id))
    for update in getattr(created, "updates", []):
        msg = getattr(update, "message", None)
        if msg and hasattr(msg, "id"):
            action = getattr(msg, "action", None)
            if action and "TopicCreate" in type(action).__name__:
                return msg.id
            return msg.id
        elif hasattr(update, "id"):
            return update.id

    # Fallback consulta
    res = await client(GetForumTopicsRequest(peer=chat_entity, offset_date=None, offset_id=0, offset_topic=0, limit=10))
    for t in getattr(res, "topics", []):
        if t.title.strip().lower() == title.strip().lower():
            return t.id
    return None


async def main():
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        print("=" * 65)
        print("COPIANDO 'MACHOS ALFA' Y 'EL BARCO' COMPLETAS A SERIES ESPAÑOLAS DEMO")
        print("=" * 65)

        src_chat = await client.get_entity(SRC_SPANISH_CHAT)
        demo_chat = await client.get_entity(DEMO_SPANISH_CHAT)
        print(f"Origen: {src_chat.title} ({src_chat.id})")
        print(f"Destino: {demo_chat.title} ({demo_chat.id})")

        # 1. Deshabilitar temporalmente la protección de reenvío en el origen
        print("\nDeshabilitando protección de contenido en origen para permitir copia...")
        toggled = False
        try:
            await client(ToggleNoForwardsRequest(peer=src_chat, enabled=False))
            toggled = True
            print("✅ noforwards deshabilitado.")
        except Exception as e:
            print(f"⚠️ Aviso noforwards: {e}")

        try:
            # ---------------------------------------------------------
            # 2. COPIAR MACHOS ALFA COMPLETA (32 EPISODIOS)
            # ---------------------------------------------------------
            print("\n--- 1. PROCESANDO MACHOS ALFA ---")
            macho_topic_id = await recreate_topic(client, demo_chat, "Machos Alfa")
            print(f"✅ Tema 'Machos Alfa' creado en Demo con ID: {macho_topic_id}")

            macho_msgs = []
            async for m in client.iter_messages(src_chat, reply_to=SRC_TOPIC_MACHOS, reverse=True):
                if is_video(m):
                    macho_msgs.append(m)

            print(f"Total de episodios encontrados en origen: {len(macho_msgs)}")
            for idx, m in enumerate(macho_msgs, 1):
                fname = m.file.name if m.file else m.id
                caption = m.text or f"Machos Alfa - {fname}"
                print(f"[{idx}/{len(macho_msgs)}] Copiando episodio: {fname}")
                await client.send_message(
                    demo_chat,
                    message=caption,
                    file=m.media,
                    reply_to=macho_topic_id
                )
                await asyncio.sleep(1.2)
            print("✅ Serie 'Machos Alfa' transferida con éxito.")

            # ---------------------------------------------------------
            # 3. COPIAR EL BARCO COMPLETA (43-44 EPISODIOS)
            # ---------------------------------------------------------
            print("\n--- 2. PROCESANDO EL BARCO ---")
            barco_topic_id = await recreate_topic(client, demo_chat, "El Barco")
            print(f"✅ Tema 'El Barco' creado en Demo con ID: {barco_topic_id}")

            barco_msgs = []
            async for m in client.iter_messages(src_chat, reply_to=SRC_TOPIC_BARCO, reverse=True):
                if is_video(m):
                    barco_msgs.append(m)

            print(f"Total de episodios encontrados en origen: {len(barco_msgs)}")
            for idx, m in enumerate(barco_msgs, 1):
                fname = m.file.name if m.file else m.id
                caption = m.text or f"El Barco - {fname}"
                print(f"[{idx}/{len(barco_msgs)}] Copiando episodio: {fname}")
                await client.send_message(
                    demo_chat,
                    message=caption,
                    file=m.media,
                    reply_to=barco_topic_id
                )
                await asyncio.sleep(1.2)
            print("✅ Serie 'El Barco' transferida con éxito.")

        finally:
            # 4. Restaurar siempre la protección en el canal original
            if toggled:
                try:
                    print("\nRestaurando protección de contenido en canal origen...")
                    await client(ToggleNoForwardsRequest(peer=src_chat, enabled=True))
                    print("✅ noforwards restaurado con éxito.")
                except Exception as e:
                    print(f"Aviso restaurando noforwards: {e}")

        print("\n" + "=" * 65)
        print("SERIES ESPAÑOLAS COMPLETAS 'MACHOS ALFA' Y 'EL BARCO' COPIADAS AL GRUPO DEMO")
        print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
