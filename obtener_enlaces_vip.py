import asyncio
import os
import json
from telethon import TelegramClient, utils
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ExportChatInviteRequest
from telethon.tl.types import ChatInviteExported

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION = os.environ["TELEGRAM_STRING_SESSION"]

TARGET_CHATS = [
    {"id": -1002146236969, "name": "REPOSITORIO DE PELÍCULAS"},
    {"id": -1002097175258, "name": "SERIES TV"},
    {"id": -1004419790119, "name": "Series Españolas"}
]

async def main():
    print("Iniciando cliente Telegram...")
    client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        print("Error: Sesion no autorizada")
        return

    vip_links = {}

    for target in TARGET_CHATS:
        chat_id = target["id"]
        name = target["name"]
        print(f"\nObteniendo enlace para: {name} (ID: {chat_id})...")
        try:
            entity = await client.get_entity(chat_id)
            # Exportar enlace permanente
            invite = await client(ExportChatInviteRequest(
                peer=entity,
                title="Acceso TeveFlipe VIP"
            ))
            if isinstance(invite, ChatInviteExported):
                link = invite.link
            else:
                link = getattr(invite, 'link', str(invite))

            print(f"  -> Enlace obtenido: {link}")
            vip_links[str(chat_id)] = {
                "id": chat_id,
                "name": name,
                "link": link
            }
        except Exception as e:
            print(f"  Error obteniendo enlace para {name}: {e}")

    with open("vip_config.json", "w", encoding="utf-8") as f:
        json.dump(vip_links, f, indent=2, ensure_ascii=False)
    print("\nGuardado en vip_config.json:")
    print(json.dumps(vip_links, indent=2, ensure_ascii=False))

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
