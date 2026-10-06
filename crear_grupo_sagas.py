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
        title = "🪐 Sagas & Franquicias - TeVeFLIPE"
        about = "Colecciones completas de sagas cinematográficas y franquicias para TeVeFLIPE."
        
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
        exported = await client(ExportChatInviteRequest(peer=chat_obj, title="Enlace Privado Sagas & Franquicias"))
        link = exported.link if isinstance(exported, ChatInviteExported) else ""
        print(f"🔗 Enlace permanente: {link}")

        sagas_config = {
            "id": chat_id,
            "title": title,
            "category": "sagas",
            "is_forum": True,
            "invite_link": link
        }
        with open("config_sagas.json", "w", encoding="utf-8") as f:
            json.dump(sagas_config, f, indent=2, ensure_ascii=False)
        print("config_sagas.json guardado con éxito.")

        # Actualizar canales_map.json si existe
        if os.path.exists("canales_map.json"):
            try:
                with open("canales_map.json", "r", encoding="utf-8") as f:
                    cmap = json.load(f)
                
                # Verificar si ya existe
                exists = any(c.get("id") == "sagas_franquicias" or c.get("produccion_id") == chat_id for c in cmap)
                if not exists:
                    cmap.append({
                        "id": "sagas_franquicias",
                        "nombre": title,
                        "bunker_id": None,
                        "bunker_nombre": None,
                        "produccion_id": chat_id,
                        "invite_link": link,
                        "categoria": "sagas",
                        "is_forum": True,
                        "ultimo_id_sincronizado": 0,
                        "activo": True
                    })
                    with open("canales_map.json", "w", encoding="utf-8") as f:
                        json.dump(cmap, f, indent=2, ensure_ascii=False)
                    print("canales_map.json actualizado con la nueva entrada de sagas.")
            except Exception as e:
                print(f"Error actualizando canales_map.json: {e}")

        print("¡Supergrupo de Sagas configurado y listo!")

if __name__ == "__main__":
    asyncio.run(main())
