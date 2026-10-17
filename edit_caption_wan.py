import asyncio
import os
import re
import sys
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")
CHANNEL_ID = -1004445508015
TOPIC_ID = 12295

async def main():
    if not SESSION_PROD:
        print("ERROR: SESSION_PROD no encontrada")
        sys.exit(1)

    print("Iniciando sesión en Producción...")
    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client:
        me = await client.get_me()
        print(f"Conectado como: {me.first_name} ({me.id})")
        channel = await client.get_entity(CHANNEL_ID)
        print(f"Canal encontrado: {channel.title}")

        messages = []
        async for msg in client.iter_messages(channel, reply_to=TOPIC_ID):
            if msg.media:
                messages.append(msg)

        # Ordenar cronológicamente (primer capítulo primero)
        messages.sort(key=lambda m: m.id)
        print(f"Total de mensajes con media en topic {TOPIC_ID}: {len(messages)}")

        for idx, msg in enumerate(messages, start=1):
            fname = msg.file.name if msg.file else ""
            new_caption = f"1x{idx:02d}"
            num_match = re.search(r"[-_ ](\d{1,3})\.", fname or "")
            if num_match:
                ep_num = int(num_match.group(1))
                new_caption = f"1x{ep_num:02d}"

            print(f"Editando mensaje {msg.id} ({fname}) -> caption='{new_caption}'")
            try:
                await client.edit_message(channel, msg.id, text=new_caption)
                print(f"  ✅ ID {msg.id} actualizado a '{new_caption}'")
            except Exception as e:
                print(f"  ❌ Error en ID {msg.id}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
