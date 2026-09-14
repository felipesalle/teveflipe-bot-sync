import asyncio
import os
import json
import random
from telethon import TelegramClient, utils
from telethon.sessions import StringSession
from telethon.tl.functions.channels import CreateChannelRequest, ToggleForumRequest
from telethon.tl.functions.messages import (
    ExportChatInviteRequest,
    CreateForumTopicRequest,
    GetForumTopicsRequest
)
from telethon.tl.types import (
    MessageMediaDocument,
    DocumentAttributeFilename,
    DocumentAttributeVideo,
    ChatInviteExported
)

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION = os.environ["TELEGRAM_STRING_SESSION"]

MOVIES_SRC_CHAT = int(os.environ.get("MOVIES_SRC_CHAT", "-1002146236969"))
SERIES_SRC_CHAT = int(os.environ.get("SERIES_SRC_CHAT", "-1002097175258"))
SPANISH_SRC_CHAT = int(os.environ.get("SPANISH_SRC_CHAT", "-1004419790119"))

CONFIG_FILE = "demo_config.json"


def is_video_message(m):
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


async def get_or_create_channel(client, title, about, is_megagroup=False, is_forum=False):
    """Busca si el canal demo ya existe; si no, lo crea y devuelve el peer, su ID y su enlace de invitación."""
    print(f"\nVerificando/Creando '{title}'...")
    
    # 1. Comprobar si ya existe en los diálogos del usuario
    existing = None
    async for dialog in client.iter_dialogs(limit=100):
        if dialog.is_channel and dialog.title.strip().lower() == title.strip().lower():
            existing = dialog.entity
            print(f"  -> Canal ya existente encontrado: ID {utils.get_peer_id(existing)}")
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

    # 3. Exportar enlace de invitación permanente
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
            about="Canal de demostración para clientes y testers de TeveFlipe. Incluye una selección de películas de muestra.",
            is_megagroup=False,
            is_forum=False
        )
        demo_data["demo_movies"] = {
            "title": "TeveFlipe - Películas (Demo)",
            "chat_id": movies_id,
            "invite_link": movies_link
        }

        # Comprobar cuántas películas ya tiene el canal demo
        existing_movies_count = 0
        async for m in client.iter_messages(movies_chat, limit=20):
            if is_video_message(m):
                existing_movies_count += 1

        print(f"Películas existentes en canal Demo: {existing_movies_count}")
        if existing_movies_count < 10:
            to_copy = 10 - existing_movies_count
            print(f"Copiando {to_copy} películas desde el canal oficial ({MOVIES_SRC_CHAT})...")
            copied = 0
            async for m in client.iter_messages(MOVIES_SRC_CHAT, limit=50):
                if is_video_message(m):
                    fname = m.file.name if m.file else m.id
                    caption = m.text or fname
                    print(f"  -> Copiando película: {fname}")
                    await client.send_message(
                        movies_chat,
                        message=caption,
                        file=m.media
                    )
                    copied += 1
                    await asyncio.sleep(2.0)
                    if copied >= to_copy:
                        break
            print(f"✅ {copied} películas copiadas al canal Demo.")

        # -------------------------------------------------------------
        # 2. GRUPO DEMO DE SERIES (FORO)
        # -------------------------------------------------------------
        print("\n--- 2. SUPERGRUPO DEMO DE SERIES (FORO) ---")
        series_chat, series_id, series_link = await get_or_create_channel(
            client,
            title="TeveFlipe - Series (Demo)",
            about="Grupo de demostración para clientes y testers de TeveFlipe. Incluye selección de series populares de muestra.",
            is_megagroup=True,
            is_forum=True
        )
        demo_data["demo_series"] = {
            "title": "TeveFlipe - Series (Demo)",
            "chat_id": series_id,
            "invite_link": series_link
        }

        # Poblaremos con 2 series de éxito: "Entre Fantasmas" y "Bones"
        series_samples = [
            {"title": "Entre Fantasmas", "src_topic": 11511, "max_eps": 10},
            {"title": "Bones", "src_topic": 10406, "max_eps": 10}
        ]

        for s_info in series_samples:
            s_title = s_info["title"]
            s_topic_id = s_info["src_topic"]
            max_eps = s_info["max_eps"]

            print(f"\nConfigurando serie de muestra: '{s_title}'...")
            demo_topic_id = await create_demo_topic(client, series_chat, s_title)
            print(f"  -> Tema en demo: ID {demo_topic_id}")

            # Contar si ya tiene episodios
            eps_count = 0
            if demo_topic_id:
                async for m in client.iter_messages(series_chat, reply_to=demo_topic_id, limit=20):
                    if is_video_message(m):
                        eps_count += 1

            if eps_count < max_eps and demo_topic_id:
                to_copy = max_eps - eps_count
                print(f"  -> Copiando {to_copy} capítulos desde el tema oficial {s_topic_id}...")
                copied = 0
                async for m in client.iter_messages(SERIES_SRC_CHAT, reply_to=s_topic_id, reverse=True, limit=50):
                    if is_video_message(m):
                        fname = m.file.name if m.file else m.id
                        caption = m.text or f"{s_title} - {fname}"
                        print(f"    -> Enviando episodio: {fname}")
                        await client.send_message(
                            series_chat,
                            message=caption,
                            file=m.media,
                            reply_to=demo_topic_id
                        )
                        copied += 1
                        await asyncio.sleep(1.5)
                        if copied >= to_copy:
                            break
                print(f"  ✅ {copied} capítulos de '{s_title}' copiados al tema demo.")

        # -------------------------------------------------------------
        # 3. GRUPO DEMO DE SERIES ESPAÑOLAS (FORO)
        # -------------------------------------------------------------
        print("\n--- 3. SUPERGRUPO DEMO DE SERIES ESPAÑOLAS (FORO) ---")
        spanish_chat, spanish_id, spanish_link = await get_or_create_channel(
            client,
            title="TeveFlipe - Series Españolas (Demo)",
            about="Grupo de demostración para clientes y testers de TeveFlipe. Incluye selección de series españolas de muestra.",
            is_megagroup=True,
            is_forum=True
        )
        demo_data["demo_spanish"] = {
            "title": "TeveFlipe - Series Españolas (Demo)",
            "chat_id": spanish_id,
            "invite_link": spanish_link
        }

        # Serie española de muestra: "Luna, El Misterio De Calenda"
        s_title = "Luna, El Misterio De Calenda"
        s_topic_id = 10002
        max_eps = 10

        print(f"\nConfigurando serie española de muestra: '{s_title}'...")
        demo_spanish_topic_id = await create_demo_topic(client, spanish_chat, s_title)
        print(f"  -> Tema en demo: ID {demo_spanish_topic_id}")

        eps_count = 0
        if demo_spanish_topic_id:
            async for m in client.iter_messages(spanish_chat, reply_to=demo_spanish_topic_id, limit=20):
                if is_video_message(m):
                    eps_count += 1

        if eps_count < max_eps and demo_spanish_topic_id:
            to_copy = max_eps - eps_count
            print(f"  -> Copiando {to_copy} capítulos desde el tema oficial {s_topic_id}...")
            copied = 0
            async for m in client.iter_messages(SERIES_SRC_CHAT, reply_to=s_topic_id, reverse=True, limit=50):
                if is_video_message(m):
                    fname = m.file.name if m.file else m.id
                    caption = m.text or f"{s_title} - {fname}"
                    print(f"    -> Enviando episodio: {fname}")
                    await client.send_message(
                        spanish_chat,
                        message=caption,
                        file=m.media,
                        reply_to=demo_spanish_topic_id
                    )
                    copied += 1
                    await asyncio.sleep(1.5)
                    if copied >= to_copy:
                        break
            print(f"  ✅ {copied} capítulos de '{s_title}' copiados al tema demo.")

        # Guardar configuración demo
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(demo_data, f, indent=2, ensure_ascii=False)

        print("\n" + "=" * 65)
        print("GRUPOS DEMO CREADOS Y CONFIGURADOS CON ÉXITO")
        print(f"1. Películas Demo: {demo_data['demo_movies']['chat_id']} | Enlace: {demo_data['demo_movies']['invite_link']}")
        print(f"2. Series Demo: {demo_data['demo_series']['chat_id']} | Enlace: {demo_data['demo_series']['invite_link']}")
        print(f"3. Series Españolas Demo: {demo_data['demo_spanish']['chat_id']} | Enlace: {demo_data['demo_spanish']['invite_link']}")
        print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
