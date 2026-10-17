import asyncio
import os
import sys
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.types import MessageMediaDocument, DocumentAttributeFilename

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")

BUNKER_80_90 = -1004316187715
BUNKER_INVITE_HASH = "iBFj892Hwak4Njcz"
PROD_80_90 = -1004467288762
OLD_MSG_ID = 4569

def get_filename(msg):
    if not msg or not msg.media:
        return ""
    if getattr(msg, "file", None) and getattr(msg.file, "name", None):
        return msg.file.name or ""
    if isinstance(msg.media, MessageMediaDocument) and msg.media.document:
        for attr in msg.media.document.attributes:
            if isinstance(attr, DocumentAttributeFilename):
                return attr.file_name or ""
    return ""

async def main():
    if not SESSION_PROD:
        print("ERROR: SESSION_PROD no encontrada")
        sys.exit(1)

    print("=== Conectando a Producción ===")
    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client:
        me = await client.get_me()
        print(f"Conectado como: {me.first_name} ({me.id})")

        # 1. Asegurar acceso al Búnker 80 y 90
        bunker_entity = None
        try:
            bunker_entity = await client.get_entity(BUNKER_80_90)
            print(f"Búnker 80 y 90 resuelto: {bunker_entity.title}")
        except Exception as e:
            print(f"Intentando unir cuenta al Búnker vía enlace de invitación... ({e})")
            try:
                updates = await client(ImportChatInviteRequest(BUNKER_INVITE_HASH))
                bunker_entity = await client.get_entity(BUNKER_80_90)
                print(f"Unido exitosamente al Búnker 80 y 90: {bunker_entity.title}")
            except errors.UserAlreadyParticipantError:
                bunker_entity = await client.get_entity(BUNKER_80_90)
                print(f"Ya era participante del Búnker: {bunker_entity.title}")
            except Exception as e2:
                print(f"Error accediendo al Búnker: {e2}")
                sys.exit(1)

        # 2. Localizar el mensaje recién copiado en el Búnker
        print("\n--- Buscando el mensaje recién copiado en Búnker 80 y 90 ---")
        target_msg = None

        # Revisar los últimos 15 mensajes del Búnker
        async for msg in client.iter_messages(bunker_entity, limit=15):
            fname = get_filename(msg)
            text = (msg.text or "").lower()
            fname_lower = fname.lower()
            print(f"Msg ID {msg.id}: {fname} | Texto: {repr(msg.text[:50] if msg.text else '')}")
            if "ruina" in fname_lower or "ruina" in text or "money pit" in fname_lower or "money pit" in text:
                target_msg = msg
                print(f"🎯 ¡Encontrada por búsqueda! ID {msg.id}: {fname}")
                break

        if not target_msg:
            # Si no salió por texto/nombre, buscar el último mensaje con video
            async for msg in client.iter_messages(bunker_entity, limit=5):
                if msg.media:
                    fname = get_filename(msg)
                    target_msg = msg
                    print(f"🎯 Seleccionado último archivo multimedia en Búnker ID {msg.id}: {fname}")
                    break

        if not target_msg:
            print("❌ No se encontró ningún mensaje nuevo en el Búnker.")
            sys.exit(1)

        chosen_filename = get_filename(target_msg)
        caption = target_msg.text or "**Esta casa es una ruina** [1986] 🇪🇸 [Castellano]"
        print(f"\nPelícula a transferir: ID {target_msg.id} | Archivo: {chosen_filename}")

        # 3. Publicar en Producción 80 y 90
        print("\n--- Publicando en Producción 80 y 90 ---")
        prod_entity = await client.get_entity(PROD_80_90)
        
        sent_msg = None
        try:
            sent_msg = await client.send_message(
                prod_entity,
                message=caption,
                file=target_msg.media
            )
            print(f"✅ ¡Publicado exitosamente en Producción! Nuevo Msg ID: {sent_msg.id}")
        except Exception as e:
            print(f"Aviso con send_message: {e}. Intentando forward...")
            try:
                sent_msg = await client.forward_messages(prod_entity, target_msg)
                print(f"✅ Reenviado exitosamente a Producción! Nuevo Msg ID: {sent_msg.id}")
            except Exception as e2:
                print(f"❌ Error publicando en Producción: {e2}")
                sys.exit(1)

        # 4. Eliminar versión anterior en inglés de Producción
        print("\n--- Limpiando versión anterior en inglés de Producción ---")
        try:
            await client.delete_messages(prod_entity, [OLD_MSG_ID])
            print(f"🗑️ Eliminado mensaje antiguo ID {OLD_MSG_ID} de Producción!")
        except Exception as e:
            print(f"Aviso al eliminar mensaje {OLD_MSG_ID}: {e}")

        # También verificar si hay algún otro mensaje con la versión en inglés
        async for msg in client.iter_messages(prod_entity, search="Esta casa es una ruina"):
            if msg.id != sent_msg.id:
                old_f = get_filename(msg)
                print(f"Encontrada otra copia en Producción ID {msg.id} ({old_f}), eliminando...")
                try:
                    await client.delete_messages(prod_entity, [msg.id])
                    print(f"🗑️ Eliminada copia ID {msg.id}")
                except Exception as e:
                    print(f"Error eliminando ID {msg.id}: {e}")

        print("\n🎉 ¡MIGRACIÓN A PRODUCCIÓN COMPLETADA CON ÉXITO!")

if __name__ == "__main__":
    asyncio.run(main())
