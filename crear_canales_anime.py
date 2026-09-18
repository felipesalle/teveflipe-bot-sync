import asyncio
import os
import json
from telethon import TelegramClient, utils
from telethon.sessions import StringSession
from telethon.tl.functions.channels import CreateChannelRequest, ToggleForumRequest
from telethon.tl.functions.messages import ExportChatInviteRequest
from telethon.tl.types import ChatInviteExported

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION = os.environ["TELEGRAM_STRING_SESSION"]

CONFIG_FILE = "anime_config.json"

async def main():
    print("=" * 60)
    print(" CREACIÓN DE CANALES PRIVADOS DE ANIME EN TELEGRAM")
    print("=" * 60)

    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        me = await client.get_me()
        print(f"👤 Conectado como: {me.first_name} (@{me.username or 'sin_username'}) [ID: {me.id}]")

        config = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except Exception:
                config = {}

        # 1. CANAL DE DIFUSIÓN: Películas Anime
        movies_title = "🎬 Películas Anime - TeveFlipe"
        movies_about = "Catálogo privado de Películas y Largometrajes Anime para TeveFlipe TV."
        movies_chat = None
        movies_id = config.get("movies_channel_id")

        if movies_id:
            try:
                movies_chat = await client.get_entity(movies_id)
                print(f"✅ Canal de Películas existente encontrado por ID: {movies_title} ({movies_id})")
            except Exception:
                movies_chat = None

        if not movies_chat:
            async for dialog in client.iter_dialogs(limit=150):
                if dialog.is_channel and not dialog.is_group and "películas anime" in dialog.title.lower():
                    movies_chat = dialog.entity
                    movies_id = utils.get_peer_id(movies_chat)
                    print(f"✅ Canal de Películas existente encontrado en diálogos: {dialog.title} ({movies_id})")
                    break

        if not movies_chat:
            print(f"🚀 Creando canal de difusión privado: '{movies_title}'...")
            res_m = await client(CreateChannelRequest(
                title=movies_title,
                about=movies_about,
                broadcast=True,
                megagroup=False
            ))
            movies_chat = res_m.chats[0]
            movies_id = utils.get_peer_id(movies_chat)
            print(f"🎉 ¡Canal de Películas Anime creado! ID: {movies_id}")

        # Exportar enlace de invitación
        movies_link = config.get("movies_channel_link", "")
        try:
            exported = await client(ExportChatInviteRequest(peer=movies_chat, title="Enlace Privado Películas Anime"))
            if isinstance(exported, ChatInviteExported):
                movies_link = exported.link
                print(f"🔗 Enlace privado Películas Anime: {movies_link}")
        except Exception as e:
            print(f"⚠️ Aviso enlace películas: {e}")

        # 2. SUPERGRUPO CON FOROS: Series Anime
        series_title = "📺 Series Anime - TeveFlipe"
        series_about = "Catálogo privado de Series Anime organizadas por Temas para TeveFlipe TV."
        series_chat = None
        series_id = config.get("series_group_id")

        if series_id:
            try:
                series_chat = await client.get_entity(series_id)
                print(f"✅ Supergrupo de Series existente encontrado por ID: {series_title} ({series_id})")
            except Exception:
                series_chat = None

        if not series_chat:
            async for dialog in client.iter_dialogs(limit=150):
                if dialog.is_group and "series anime" in dialog.title.lower():
                    series_chat = dialog.entity
                    series_id = utils.get_peer_id(series_chat)
                    print(f"✅ Supergrupo de Series existente encontrado en diálogos: {dialog.title} ({series_id})")
                    break

        if not series_chat:
            print(f"🚀 Creando supergrupo privado con temas/foros: '{series_title}'...")
            res_s = await client(CreateChannelRequest(
                title=series_title,
                about=series_about,
                broadcast=False,
                megagroup=True,
                forum=True
            ))
            series_chat = res_s.chats[0]
            series_id = utils.get_peer_id(series_chat)
            print(f"🎉 ¡Supergrupo de Series Anime creado! ID: {series_id}")

        # Habilitar foros / temas explícitamente
        try:
            await client(ToggleForumRequest(channel=series_chat, enabled=True, tabs=False))
            print("✨ Modo Foro/Temas activado correctamente en Series Anime.")
        except Exception as e:
            print(f"ℹ️ Foros ya activos o aviso: {e}")

        # Exportar enlace de invitación
        series_link = config.get("series_group_link", "")
        try:
            exported_s = await client(ExportChatInviteRequest(peer=series_chat, title="Enlace Privado Series Anime"))
            if isinstance(exported_s, ChatInviteExported):
                series_link = exported_s.link
                print(f"🔗 Enlace privado Series Anime: {series_link}")
        except Exception as e:
            print(f"⚠️ Aviso enlace series: {e}")

        # Guardar en archivo de configuración
        final_config = {
            "source_chat_id": -1002257262928,
            "source_topic_id": 316312,
            "movies_channel_id": movies_id,
            "movies_channel_title": movies_title,
            "movies_channel_link": movies_link,
            "series_group_id": series_id,
            "series_group_title": series_title,
            "series_group_link": series_link
        }

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(final_config, f, indent=2, ensure_ascii=False)

        print("\n" + "=" * 60)
        print(" RESUMEN DE CANALES CREADOS EXITOSAMENTE")
        print("=" * 60)
        print(f"🎬 Películas Anime: ID {movies_id} | Link: {movies_link}")
        print(f"📺 Series Anime:    ID {series_id} | Link: {series_link}")
        print(f"📁 Configuración guardada en: {CONFIG_FILE}")

if __name__ == "__main__":
    asyncio.run(main())
