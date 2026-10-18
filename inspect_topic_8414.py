import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetForumTopicsRequest

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")
SESSION_BUNKER = os.getenv("SESSION_BUNKER", "")

PROD_SERIES = -1004331019870
BUNKER_SERIES = -1002097175258
TOPIC_ID = 8414

async def main():
    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client:
        print("=== CONECTADO A TELEGRAM (PRODUCCIÓN) ===")
        prod_entity = await client.get_entity(PROD_SERIES)
        print(f"Canal: {prod_entity.title} ({prod_entity.id})")

        # Mensaje raíz del topic
        topic_title = f"Topic {TOPIC_ID}"
        try:
            root_msg = await client.get_messages(prod_entity, ids=TOPIC_ID)
            if root_msg:
                print(f"Mensaje raíz (ID {root_msg.id}): text={repr(root_msg.text)}, action={root_msg.action}")
                if root_msg.action and hasattr(root_msg.action, 'title'):
                    topic_title = root_msg.action.title
                    print(f"Título del Tema según acción raíz: {topic_title}")
        except Exception as e:
            print(f"Error al leer mensaje raíz: {e}")

        print(f"\n=== MENSAJES DENTRO DEL TEMA {TOPIC_ID} ({topic_title}) ===")
        count = 0
        async for m in client.iter_messages(prod_entity, reply_to=TOPIC_ID, reverse=True):
            count += 1
            fn = m.file.name if m.file else (m.text[:30] if m.text else "Sin archivo/texto")
            sz = f"{m.file.size / (1024*1024):.1f} MB" if m.file else "-"
            txt = (m.text or "").replace('\n', ' ')[:70]
            print(f"[{count:03d}] ID {m.id} | Archivo: {fn} | Size: {sz} | Text: {txt}")

        print(f"\nTotal mensajes encontrados en topic {TOPIC_ID}: {count}")

if __name__ == "__main__":
    asyncio.run(main())
