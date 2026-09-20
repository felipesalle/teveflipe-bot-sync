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

async def main():
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        title = "📺 Series Turcas y Telenovelas - TeveFlipe"
        about = "Catálogo de Series Turcas, Telenovelas y producciones latinas para TeveFlipe."
        
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

        exported = await client(ExportChatInviteRequest(peer=chat_obj, title="Enlace Privado Turcas y Telenovelas"))
        link = exported.link if isinstance(exported, ChatInviteExported) else ""
        print(f"🔗 Enlace permanente: {link}")

        with open("config_supergrupos_series.json", "r", encoding="utf-8") as f:
            cfg = json.load(f)

        cfg["turcas_y_telenovelas"] = {
            "id": chat_id,
            "title": title,
            "category": "series",
            "is_forum": True,
            "invite_link": link
        }

        with open("config_supergrupos_series.json", "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        print("Configuración actualizada!")

if __name__ == "__main__":
    asyncio.run(main())
