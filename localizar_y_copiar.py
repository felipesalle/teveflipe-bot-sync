import asyncio
import os
import json
import re
from telethon import TelegramClient, utils
from telethon.sessions import StringSession
from telethon.tl.functions.messages import (
    ToggleNoForwardsRequest,
    CreateForumTopicRequest,
    GetForumTopicsRequest
)
from telethon.tl.types import MessageMediaDocument, DocumentAttributeFilename, DocumentAttributeVideo

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION = os.environ["TELEGRAM_STRING_SESSION"]

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


async def get_or_create_topic(client, chat_entity, title):
    try:
        res = await client(GetForumTopicsRequest(peer=chat_entity, offset_date=None, offset_id=0, offset_topic=0, limit=20))
        for t in getattr(res, "topics", []):
            if t.title.strip().lower() == title.strip().lower():
                return t.id
    except Exception:
        pass
    import random
    rand_id = random.randint(1, 2**63 - 1)
    created = await client(CreateForumTopicRequest(peer=chat_entity, title=title, random_id=rand_id))
    for update in getattr(created, "updates", []):
        msg = getattr(update, "message", None)
        if msg and hasattr(msg, "id"):
            return msg.id
        elif hasattr(update, "id"):
            return update.id
    return None


async def main():
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        print("=" * 65)
        print("BUSCANDO 'MACHOS ALFA' Y 'EL BARCO' EN LOS CANALES DEL USUARIO")
        print("=" * 65)

        demo_chat = await client.get_entity(DEMO_SPANISH_CHAT)
        print(f"Destino: {demo_chat.title} ({demo_chat.id})")

        # 1. Buscar en todos los diálogos
        dialogs = await client.get_dialogs(limit=150)
        print(f"Total de diálogos analizados: {len(dialogs)}")

        found_macho_chat = None
        found_macho_msgs = []
        found_barco_chat = None
        found_barco_msgs = []

        for d in dialogs:
            title = d.title or ""
            entity = d.entity
            peer_id = utils.get_peer_id(entity)

            # Buscar mensajes de Machos Alfa
            try:
                macho_matches = []
                async for m in client.iter_messages(entity, search="Macho", limit=100):
                    if is_video(m):
                        fname = (m.file.name or "") if m.file else ""
                        text = m.text or ""
                        if "macho" in fname.lower() or "macho" in text.lower():
                            macho_matches.append(m)
                
                if macho_matches:
                    print(f"🎯 Encontrados {len(macho_matches)} videos de 'Macho Alfa' en: '{title}' ({peer_id})")
                    if len(macho_matches) > len(found_macho_msgs):
                        found_macho_chat = entity
                        found_macho_msgs = macho_matches
            except Exception as e:
                pass

            # Buscar mensajes de El Barco
            try:
                barco_matches = []
                async for m in client.iter_messages(entity, search="Barco", limit=100):
                    if is_video(m):
                        fname = (m.file.name or "") if m.file else ""
                        text = m.text or ""
                        if "barco" in fname.lower() or "barco" in text.lower():
                            barco_matches.append(m)

                if barco_matches:
                    print(f"🎯 Encontrados {len(barco_matches)} videos de 'El Barco' en: '{title}' ({peer_id})")
                    if len(barco_matches) > len(found_barco_msgs):
                        found_barco_chat = entity
                        found_barco_msgs = barco_matches
            except Exception as e:
                pass

        # 2. Si hay foros de series, revisar también los temas de los supergrupos
        series_groups = [d.entity for d in dialogs if getattr(d.entity, "forum", False)]
        print(f"\nSupergrupos con foros detectados: {len(series_groups)}")
        for sg in series_groups:
            sg_title = sg.title or ""
            print(f"Inspeccionando temas en foro: '{sg_title}' ({sg.id})...")
            try:
                topics_res = await client(GetForumTopicsRequest(peer=sg, offset_date=None, offset_id=0, offset_topic=0, limit=100))
                for top in getattr(topics_res, "topics", []):
                    top_title = getattr(top, "title", "")
                    top_id = getattr(top, "id", 0)
                    if "macho" in top_title.lower() or "alfa" in top_title.lower():
                        print(f"  -> Tema Macho Alfa detectado en '{sg_title}': '{top_title}' (Topic ID {top_id})")
                        topic_msgs = []
                        async for tm in client.iter_messages(sg, reply_to=top_id, reverse=True):
                            if is_video(tm):
                                topic_msgs.append(tm)
                        if len(topic_msgs) > len(found_macho_msgs):
                            found_macho_chat = sg
                            found_macho_msgs = topic_msgs
                    
                    if "barco" in top_title.lower():
                        print(f"  -> Tema El Barco detectado en '{sg_title}': '{top_title}' (Topic ID {top_id})")
                        topic_msgs = []
                        async for tm in client.iter_messages(sg, reply_to=top_id, reverse=True):
                            if is_video(tm):
                                topic_msgs.append(tm)
                        if len(topic_msgs) > len(found_barco_msgs):
                            found_barco_chat = sg
                            found_barco_msgs = topic_msgs
            except Exception as e:
                print(f"  Aviso listando temas en {sg_title}: {e}")

        # -------------------------------------------------------------
        # 3. COPIAR MACHOS ALFA AL CANAL DEMO
        # -------------------------------------------------------------
        if found_macho_msgs:
            print(f"\n--- COPIANDO {len(found_macho_msgs)} EPISODIOS DE MACHOS ALFA ---")
            # Si el chat origen tiene noforwards, intentar deshabilitarlo temporalmente
            toggled = False
            try:
                print("Intentando deshabilitar noforwards temporalmente...")
                await client(ToggleNoForwardsRequest(peer=found_macho_chat, enabled=False))
                toggled = True
                print("✅ noforwards deshabilitado temporalmente.")
            except Exception as e:
                print(f"Aviso noforwards: {e}")

            macho_topic_id = await get_or_create_topic(client, demo_chat, "Machos Alfa")
            print(f"Tema 'Machos Alfa' en Demo ID: {macho_topic_id}")
            
            # Ordenar mensajes cronológicamente
            found_macho_msgs = sorted(found_macho_msgs, key=lambda x: x.id)
            for idx, m in enumerate(found_macho_msgs, 1):
                fname = m.file.name if m.file else m.id
                caption = m.text or f"Machos Alfa - {fname}"
                print(f"[{idx}/{len(found_macho_msgs)}] Copiando: {fname}")
                try:
                    await client.send_message(
                        demo_chat,
                        message=caption,
                        file=m.media,
                        reply_to=macho_topic_id
                    )
                    await asyncio.sleep(1.2)
                except Exception as e:
                    print(f"  Error copiando episodio: {e}")

            if toggled:
                try:
                    await client(ToggleNoForwardsRequest(peer=found_macho_chat, enabled=True))
                    print("✅ noforwards restaurado.")
                except Exception:
                    pass
        else:
            print("\n❌ No se encontraron mensajes de 'Machos Alfa'.")

        # -------------------------------------------------------------
        # 4. COPIAR EL BARCO AL CANAL DEMO
        # -------------------------------------------------------------
        if found_barco_msgs:
            print(f"\n--- COPIANDO {len(found_barco_msgs)} EPISODIOS DE EL BARCO ---")
            toggled = False
            try:
                print("Intentando deshabilitar noforwards temporalmente...")
                await client(ToggleNoForwardsRequest(peer=found_barco_chat, enabled=False))
                toggled = True
                print("✅ noforwards deshabilitado temporalmente.")
            except Exception as e:
                print(f"Aviso noforwards: {e}")

            barco_topic_id = await get_or_create_topic(client, demo_chat, "El Barco")
            print(f"Tema 'El Barco' en Demo ID: {barco_topic_id}")

            found_barco_msgs = sorted(found_barco_msgs, key=lambda x: x.id)
            for idx, m in enumerate(found_barco_msgs, 1):
                fname = m.file.name if m.file else m.id
                caption = m.text or f"El Barco - {fname}"
                print(f"[{idx}/{len(found_barco_msgs)}] Copiando: {fname}")
                try:
                    await client.send_message(
                        demo_chat,
                        message=caption,
                        file=m.media,
                        reply_to=barco_topic_id
                    )
                    await asyncio.sleep(1.2)
                except Exception as e:
                    print(f"  Error copiando episodio: {e}")

            if toggled:
                try:
                    await client(ToggleNoForwardsRequest(peer=found_barco_chat, enabled=True))
                    print("✅ noforwards restaurado.")
                except Exception:
                    pass
        else:
            print("\n❌ No se encontraron mensajes de 'El Barco'.")

        print("\n" + "=" * 65)
        print("PROCESO DE COPIA DE MACHOS ALFA Y EL BARCO FINALIZADO")
        print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
