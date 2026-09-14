import asyncio
import os
import json
import random
from collections import defaultdict
from telethon import TelegramClient, utils
from telethon.sessions import StringSession
from telethon.tl.functions.channels import CreateChannelRequest, ToggleForumRequest
from telethon.tl.functions.messages import (
    ExportChatInviteRequest,
    CreateForumTopicRequest,
    GetForumTopicsRequest
)
from telethon.tl.types import ChatInviteExported

from sync_bot import (
    clean_series_title,
    extract_file_name,
    is_video_message,
    is_junk_series_title
)

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION = os.environ["TELEGRAM_STRING_SESSION"]

# Canales origen (desprotegidos para reenvío libre)
MOVIES_SRC_CHAT = int(os.environ.get("MOVIES_SRC_CHAT", "-1001905652210"))
MOVIES_SRC_TOPIC = int(os.environ.get("MOVIES_SRC_TOPIC", "1605935"))

SERIES_SRC_CHAT = int(os.environ.get("SERIES_SRC_CHAT", "-1002257262928"))
SERIES_SRC_TOPIC = int(os.environ.get("SERIES_SRC_TOPIC", "157592"))

SPANISH_SRC_CHAT = int(os.environ.get("SPANISH_SRC_CHAT", "-1002160549536"))
SPANISH_SRC_TOPIC = int(os.environ.get("SPANISH_SRC_TOPIC", "21"))

CONFIG_FILE = "demo_config.json"


async def get_or_create_channel(client, title, about, is_megagroup=False, is_forum=False):
    """Busca si el canal demo ya existe; si no, lo crea y devuelve el peer, su ID y su enlace de invitación."""
    print(f"\nVerificando/Creando '{title}'...")
    
    # 1. Comprobar si ya existe en los diálogos del usuario
    existing = None
    async for dialog in client.iter_dialogs(limit=120):
        if dialog.is_channel and dialog.title.strip().lower() == title.strip().lower():
            existing = dialog.entity
            print(f"  -> Canal existente encontrado: ID {utils.get_peer_id(existing)}")
            break

    chat = existing
    if not chat:
        print(f"  -> Creando nuevo canal en Telegram...")
        created = await client(CreateChannelRequest(
            title=title,
            about=about,
            broadcast=not is_megagroup,
            megagroup=is_megagroup,
            forum=is_forum
        ))
        chat = created.chats[0]
        print(f"  -> Creado con éxito! ID: {utils.get_peer_id(chat)}")

    # 2. Habilitar foro si es supergrupo
    if is_megagroup and is_forum:
        try:
            await client(ToggleForumRequest(channel=chat, enabled=True, tabs=False))
            print("  -> Foros/Temas habilitados.")
        except Exception as e:
            print(f"  -> Aviso foros: {e}")

    # 3. Exportar enlace de invitación
    invite_link = ""
    try:
        exported = await client(ExportChatInviteRequest(peer=chat, title="Enlace Demo Clientes"))
        if isinstance(exported, ChatInviteExported):
            invite_link = exported.link
            print(f"  -> Enlace de invitación: {invite_link}")
    except Exception as e:
        print(f"  -> Aviso enlace invitación: {e}")

    return chat, utils.get_peer_id(chat), invite_link


async def create_demo_topic(client, chat_entity, title):
    """Crea un tema en el foro demo si no existe ya."""
    try:
        res = await client(GetForumTopicsRequest(peer=chat_entity, offset_date=None, offset_id=0, offset_topic=0, limit=20))
        for t in getattr(res, "topics", []):
            if t.title.strip().lower() == title.strip().lower():
                return t.id
    except Exception:
        pass

    try:
        rand_id = random.randint(1, 2**63 - 1)
        created = await client(CreateForumTopicRequest(
            peer=chat_entity,
            title=title,
            random_id=rand_id
        ))
        for update in getattr(created, "updates", []):
            msg = getattr(update, "message", None)
            if msg and hasattr(msg, "id"):
                action = getattr(msg, "action", None)
                if action and "TopicCreate" in type(action).__name__:
                    return msg.id
                return msg.id
            elif hasattr(update, "id"):
                return update.id
    except Exception as e:
        print(f"  -> Error creando tema '{title}': {e}")
    return None


async def main():
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        print("=" * 65)
        print("CREACIÓN Y CONFIGURACIÓN DE GRUPOS DEMO / PRUEBA TEVEFLIPE")
        print("=" * 65)

        demo_data = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    demo_data = json.load(f)
            except Exception:
                pass

        # -------------------------------------------------------------
        # 1. CANAL DEMO DE PELÍCULAS
        # -------------------------------------------------------------
        print("\n--- 1. CANAL DEMO DE PELÍCULAS ---")
        movies_chat, movies_id, movies_link = await get_or_create_channel(
            client,
            title="TeveFlipe - Películas (Demo)",
            about="Canal de demostración para clientes y testers de TeveFlipe. Incluye una selección de 10 películas de muestra.",
            is_megagroup=False,
            is_forum=False
        )
        demo_data["demo_movies"] = {
            "title": "TeveFlipe - Películas (Demo)",
            "chat_id": movies_id,
            "invite_link": movies_link
        }

        # Contar cuántas películas ya tiene
        existing_movies = 0
        async for m in client.iter_messages(movies_chat, limit=20):
            if is_video_message(m):
                existing_movies += 1

        print(f"Películas existentes en canal Demo: {existing_movies}")
        if existing_movies < 10:
            to_copy = 10 - existing_movies
            print(f"Copiando {to_copy} películas desde el canal origen ({MOVIES_SRC_CHAT})...")
            copied = 0
            async for m in client.iter_messages(
                MOVIES_SRC_CHAT,
                reply_to=MOVIES_SRC_TOPIC if MOVIES_SRC_TOPIC else None,
                limit=60
            ):
                if is_video_message(m):
                    fname = extract_file_name(m) or (m.file.name if m.file else m.id)
                    caption = m.text or str(fname)
                    print(f"  -> Copiando película: {fname}")
                    try:
                        await client.send_message(
                            movies_chat,
                            message=caption,
                            file=m.media
                        )
                        copied += 1
                        await asyncio.sleep(2.0)
                        if copied >= to_copy:
                            break
                    except Exception as e:
                        print(f"    Aviso enviando: {e}")
            print(f"✅ {copied} películas copiadas al canal Demo.")

        # -------------------------------------------------------------
        # 2. GRUPO DEMO DE SERIES (FORO)
        # -------------------------------------------------------------
        print("\n--- 2. SUPERGRUPO DEMO DE SERIES (FORO) ---")
        series_chat, series_id, series_link = await get_or_create_channel(
            client,
            title="TeveFlipe - Series (Demo)",
            about="Grupo de demostración para clientes y testers de TeveFlipe. Incluye series populares de muestra.",
            is_megagroup=True,
            is_forum=True
        )
        demo_data["demo_series"] = {
            "title": "TeveFlipe - Series (Demo)",
            "chat_id": series_id,
            "invite_link": series_link
        }

        # Recopilar episodios de series del canal origen
        print(f"Escaneando series del canal origen ({SERIES_SRC_CHAT})...")
        series_episodes = defaultdict(list)
        active_series = None
        
        async for m in client.iter_messages(
            SERIES_SRC_CHAT,
            reply_to=SERIES_SRC_TOPIC if SERIES_SRC_TOPIC else None,
            limit=400,
            reverse=True
        ):
            if not m.media and m.text:
                cand = clean_series_title(m.text, is_filename=False)
                if cand and not is_junk_series_title(cand):
                    active_series = cand
            elif is_video_message(m):
                fname = extract_file_name(m)
                v_title = clean_series_title(fname, is_filename=True) if fname else None
                if not v_title and m.text:
                    v_title = clean_series_title(m.text, is_filename=False)
                if v_title and not is_junk_series_title(v_title):
                    active_series = v_title
                if active_series and not is_junk_series_title(active_series):
                    if len(series_episodes[active_series]) < 10:
                        series_episodes[active_series].append(m)

        # Seleccionar las 2 series con más episodios encontrados
        sorted_series = sorted(series_episodes.items(), key=lambda x: len(x[1]), reverse=True)
        chosen_series = sorted_series[:2]
        print(f"Series elegidas para demo: {[s[0] for s in chosen_series]}")

        for s_title, msgs in chosen_series:
            print(f"\nConfigurando tema de serie: '{s_title}' ({len(msgs)} episodios)...")
            topic_id = await create_demo_topic(client, series_chat, s_title)
            
            # Contar episodios ya enviados
            existing_eps = 0
            if topic_id:
                async for em in client.iter_messages(series_chat, reply_to=topic_id, limit=20):
                    if is_video_message(em):
                        existing_eps += 1

            if existing_eps < len(msgs) and topic_id:
                to_send = msgs[existing_eps:]
                for m in to_send:
                    fname = extract_file_name(m) or (m.file.name if m.file else m.id)
                    caption = m.text or f"{s_title} - {fname}"
                    print(f"  -> Enviando episodio: {fname}")
                    try:
                        await client.send_message(
                            series_chat,
                            message=caption,
                            file=m.media,
                            reply_to=topic_id
                        )
                        await asyncio.sleep(1.5)
                    except Exception as e:
                        print(f"    Aviso enviando episodio: {e}")
                print(f"  ✅ Episodios de '{s_title}' listos en demo.")

        # -------------------------------------------------------------
        # 3. GRUPO DEMO DE SERIES ESPAÑOLAS (FORO)
        # -------------------------------------------------------------
        print("\n--- 3. SUPERGRUPO DEMO DE SERIES ESPAÑOLAS (FORO) ---")
        spanish_chat, spanish_id, spanish_link = await get_or_create_channel(
            client,
            title="TeveFlipe - Series Españolas (Demo)",
            about="Grupo de demostración para clientes y testers de TeveFlipe. Incluye series españolas de muestra.",
            is_megagroup=True,
            is_forum=True
        )
        demo_data["demo_spanish"] = {
            "title": "TeveFlipe - Series Españolas (Demo)",
            "chat_id": spanish_id,
            "invite_link": spanish_link
        }

        # Escanear series españolas del canal origen
        print(f"Escaneando series españolas del canal origen ({SPANISH_SRC_CHAT})...")
        spanish_episodes = defaultdict(list)
        active_spanish = None

        async for m in client.iter_messages(
            SPANISH_SRC_CHAT,
            reply_to=SPANISH_SRC_TOPIC if SPANISH_SRC_TOPIC else None,
            limit=250,
            reverse=True
        ):
            if not m.media and m.text:
                cand = clean_series_title(m.text, is_filename=False)
                if cand and not is_junk_series_title(cand):
                    active_spanish = cand
            elif is_video_message(m):
                fname = extract_file_name(m)
                v_title = clean_series_title(fname, is_filename=True) if fname else None
                if not v_title and m.text:
                    v_title = clean_series_title(m.text, is_filename=False)
                if v_title and not is_junk_series_title(v_title):
                    active_spanish = v_title
                if active_spanish and not is_junk_series_title(active_spanish):
                    if len(spanish_episodes[active_spanish]) < 10:
                        spanish_episodes[active_spanish].append(m)

        sorted_spanish = sorted(spanish_episodes.items(), key=lambda x: len(x[1]), reverse=True)
        chosen_spanish = sorted_spanish[:2]
        print(f"Series españolas elegidas para demo: {[s[0] for s in chosen_spanish]}")

        for s_title, msgs in chosen_spanish:
            print(f"\nConfigurando tema de serie española: '{s_title}' ({len(msgs)} episodios)...")
            topic_id = await create_demo_topic(client, spanish_chat, s_title)
            
            existing_eps = 0
            if topic_id:
                async for em in client.iter_messages(spanish_chat, reply_to=topic_id, limit=20):
                    if is_video_message(em):
                        existing_eps += 1

            if existing_eps < len(msgs) and topic_id:
                to_send = msgs[existing_eps:]
                for m in to_send:
                    fname = extract_file_name(m) or (m.file.name if m.file else m.id)
                    caption = m.text or f"{s_title} - {fname}"
                    print(f"  -> Enviando episodio: {fname}")
                    try:
                        await client.send_message(
                            spanish_chat,
                            message=caption,
                            file=m.media,
                            reply_to=topic_id
                        )
                        await asyncio.sleep(1.5)
                    except Exception as e:
                        print(f"    Aviso enviando episodio: {e}")
                print(f"  ✅ Episodios de '{s_title}' listos en demo.")

        # Guardar archivo demo_config.json
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(demo_data, f, indent=2, ensure_ascii=False)

        print("\n" + "=" * 65)
        print("GRUPOS DEMO CREADOS Y CONFIGURADOS CON ÉXITO")
        print(f"1. Películas Demo: {demo_data['demo_movies']['chat_id']}")
        print(f"   Enlace: {demo_data['demo_movies']['invite_link']}")
        print(f"2. Series Demo: {demo_data['demo_series']['chat_id']}")
        print(f"   Enlace: {demo_data['demo_series']['invite_link']}")
        print(f"3. Series Españolas Demo: {demo_data['demo_spanish']['chat_id']}")
        print(f"   Enlace: {demo_data['demo_spanish']['invite_link']}")
        print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
