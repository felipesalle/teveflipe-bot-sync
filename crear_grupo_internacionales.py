import asyncio
import os
import json
from telethon import TelegramClient, utils
from telethon.sessions import StringSession
from telethon.tl.functions.channels import CreateChannelRequest, ToggleForumRequest
from telethon.tl.functions.messages import ExportChatInviteRequest
from telethon.tl.types import ChatInviteExported

API_ID = int(os.environ.get("TELEGRAM_API_ID", "28045969"))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION = os.environ["TELEGRAM_STRING_SESSION"]

async def main():
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        title = "📺 Series TV - TeveFlipe"
        about = "Catálogo de Series Internacionales y de plataformas (Netflix, HBO Max, Prime, Apple TV) para TeveFlipe."
        
        print(f"🚀 Creando nuevo supergrupo privado: '{title}'...")
        res = await client(CreateChannelRequest(
            title=title,
            about=about,
            broadcast=False,
            megagroup=True,
            forum=True
        ))
        chat_obj = res.chats[0]
        chat_id = utils.get_peer_id(chat_obj)
        print(f"🎉 Creado con éxito! ID: {chat_id}")

        await client(ToggleForumRequest(channel=chat_obj, enabled=True, tabs=False))
        print("✨ Foros habilitados.")

        exported = await client(ExportChatInviteRequest(peer=chat_obj, title="Enlace Privado Series Internacionales"))
        link = exported.link if isinstance(exported, ChatInviteExported) else ""
        print(f"🔗 Enlace permanente: {link}")

        config_path = "config_supergrupos_series.json"
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        cfg["internacionales"] = {
            "id": chat_id,
            "title": title,
            "category": "serie",
            "is_forum": True,
            "invite_link": link
        }

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        print(f"Configuración actualizada en {config_path}!")
        print(f"RESULT_ID={chat_id}")
        print(f"RESULT_LINK={link}")

if __name__ == "__main__":
    asyncio.run(main())
