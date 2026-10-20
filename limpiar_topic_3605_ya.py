import asyncio
import os
import sys
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")
PROD_SERIES = -1004331019870
TOPIC_ANGIE = 3605

async def main():
    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client_prod:
        prod_ent = await client_prod.get_entity(PROD_SERIES)
        
        # Obtener todos los mensajes en el topic 3605 excepto el mensaje de creación (3605)
        to_delete = []
        async for m in client_prod.iter_messages(prod_ent, reply_to=TOPIC_ANGIE):
            if m.id == TOPIC_ANGIE:
                continue
            # Si es la sinopsis pura (texto largo), podemos conservarla o si no borrar todo lo que no sea el topic
            if m.text and "Angie Tribeca (Serie de TV, 2016" in m.text and not m.media:
                print(f"Conservando sinopsis: Msg ID {m.id}")
                continue
            to_delete.append(m.id)

        print(f"Borrando {len(to_delete)} mensajes erróneos (fotos/audios/duplicados) en topic {TOPIC_ANGIE}...")
        if to_delete:
            await client_prod.delete_messages(prod_ent, to_delete)
            print("✅ Mensajes erróneos eliminados completamente.")
        else:
            print("No había mensajes para borrar.")

if __name__ == "__main__":
    asyncio.run(main())
