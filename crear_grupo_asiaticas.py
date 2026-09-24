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
        title = "📺 Series Asiáticas - TeveFlipe"
        about = "Catálogo de Doramas, K-Dramas, C-Dramas y Series Asiáticas para TeveFlipe."
        
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
        print(f"🎉 ¡Creado con éxito! ID: {chat_id}")

        await asyncio.sleep(2.0)
        await client(ToggleForumRequest(channel=chat_obj, enabled=True, tabs=False))
        print("✨ Foros habilitados.")

        await asyncio.sleep(2.0)
        exported = await client(ExportChatInviteRequest(peer=chat_obj, title="Enlace Privado Series Asiáticas"))
        link = exported.link if isinstance(exported, ChatInviteExported) else ""
        print(f"🔗 Enlace permanente: {link}")

        # Update or create config_asiaticas.json
        asiaticas_config = {
            "id": chat_id,
            "title": title,
            "category": "asiaticas",
            "is_forum": True,
            "invite_link": link,
            "source_chat_id": -1002160549536,
            "source_topic_id": 10
        }
        with open("config_asiaticas.json", "w", encoding="utf-8") as f:
            json.dump(asiaticas_config, f, indent=2, ensure_ascii=False)

        # Also update config_supergrupos_series.json
        if os.path.exists("config_supergrupos_series.json"):
            try:
                with open("config_supergrupos_series.json", "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                cfg["series_asiaticas"] = {
                    "id": chat_id,
                    "title": title,
                    "category": "asiaticas",
                    "is_forum": True,
                    "invite_link": link
                }
                with open("config_supergrupos_series.json", "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=2, ensure_ascii=False)
                print("config_supergrupos_series.json actualizado con éxito!")
            except Exception as e:
                print(f"Aviso actualizando config_supergrupos_series.json: {e}")

        print("Todo listo para iniciar la sincronización.")

if __name__ == "__main__":
    asyncio.run(main())
