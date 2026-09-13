import asyncio
import os
import re
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION = os.environ["TELEGRAM_STRING_SESSION"]
TARGET_CHAT = int(os.environ["TARGET_CHAT"])

TOPIC_CUENTAME = 2662
TOPIC_7VIDAS = 5187
TOPIC_ANHQV = 4518
TOPIC_AIDA = 2350

async def main():
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        chat = await client.get_entity(TARGET_CHAT)
        print("=" * 60)
        print("REVISANDO Y CORRIGIENDO EPISODIOS DESVIADOS")
        print("=" * 60)

        # 1. Revisar tema de Cuéntame Cómo Pasó (Topic 2662)
        print("\n--- 1. Revisando tema 'Cuéntame Cómo Pasó' (Topic 2662) ---")
        async for msg in client.iter_messages(chat, reply_to=TOPIC_CUENTAME, limit=100):
            text = (msg.text or "").lower()
            fname = ""
            if msg.file and msg.file.name:
                fname = msg.file.name.lower()
            combined = f"{text} {fname}"

            if "7 vidas" in combined or "siete vidas" in combined:
                print(f"🔄 Encontrado capítulo de 7 Vidas en Cuéntame (Msg ID {msg.id}): {msg.file.name if msg.file else msg.text}")
                # Reenviar a 7 Vidas
                await client.send_message(
                    chat,
                    message=msg.text or (msg.file.name if msg.file else ""),
                    file=msg.media,
                    reply_to=TOPIC_7VIDAS
                )
                print(f"✅ Reenviado al tema '7 Vidas' (Topic {TOPIC_7VIDAS})")
                # Borrar del tema equivocado
                await client.delete_messages(chat, [msg.id])
                print(f"🗑️ Eliminado de 'Cuéntame' (Msg ID {msg.id})")
                await asyncio.sleep(2)

        # 2. Revisar tema de 7 Vidas (Topic 5187)
        print("\n--- 2. Revisando tema '7 Vidas' (Topic 5187) ---")
        async for msg in client.iter_messages(chat, reply_to=TOPIC_7VIDAS, limit=200):
            text = (msg.text or "").lower()
            fname = ""
            if msg.file and msg.file.name:
                fname = msg.file.name.lower()
            combined = f"{text} {fname}"

            # ¿Es de Aquí No Hay Quien Viva? ("érase un", "érase una", "anhqv", o temporada 3-5 que sea de ANHQV)
            is_anhqv = False
            if "érase" in combined or "erase" in combined or "anhqv" in combined or "paripé" in combined or "adiós" in combined:
                is_anhqv = True

            # ¿Es de Aída?
            is_aida = False
            if ("aida" in combined or "aída" in combined) and ("1x" in combined or "2x" in combined or "3x" in combined or "temporada" in combined or "capitulo" in combined or "capítulo" in combined):
                is_aida = True

            if is_anhqv:
                print(f"🔄 Encontrado capítulo de ANHQV en 7 Vidas (Msg ID {msg.id}): {msg.file.name if msg.file else msg.text}")
                await client.send_message(
                    chat,
                    message=msg.text or (msg.file.name if msg.file else ""),
                    file=msg.media,
                    reply_to=TOPIC_ANHQV
                )
                print(f"✅ Reenviado al tema 'Aquí No Hay Quien Viva' (Topic {TOPIC_ANHQV})")
                await client.delete_messages(chat, [msg.id])
                print(f"🗑️ Eliminado de '7 Vidas' (Msg ID {msg.id})")
                await asyncio.sleep(2)

            elif is_aida:
                print(f"🔄 Encontrado capítulo de Aída en 7 Vidas (Msg ID {msg.id}): {msg.file.name if msg.file else msg.text}")
                await client.send_message(
                    chat,
                    message=msg.text or (msg.file.name if msg.file else ""),
                    file=msg.media,
                    reply_to=TOPIC_AIDA
                )
                print(f"✅ Reenviado al tema 'Aída' (Topic {TOPIC_AIDA})")
                await client.delete_messages(chat, [msg.id])
                print(f"🗑️ Eliminado de '7 Vidas' (Msg ID {msg.id})")
                await asyncio.sleep(2)

        print("\n" + "=" * 60)
        print("LIMPIEZA Y REUBICACIÓN COMPLETADA EXITOSAMENTE")
        print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
