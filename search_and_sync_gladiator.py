import os
import asyncio
from telethon.sync import TelegramClient
from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto

async def main():
    api_id = int(os.environ.get('TELEGRAM_API_ID'))
    api_hash = os.environ.get('TELEGRAM_API_HASH')
    
    bunker_session = os.environ.get('SESSION_BUNKER')
    prod_session = os.environ.get('SESSION_PROD')

    # IDs de los canales de Películas Estrenos
    bunker_channel_id = -1002146236969 # 🎬 Películas Estrenos - TeVeFLIPE (Búnker)
    prod_channel_id = -1003763464899 # 🎬 Películas Estrenos - TeVeFLIPE (Producción)
    
    search_query = "Gladiator"
    
    print(f"Iniciando búsqueda de '{search_query}' en el Búnker de películas...")

    # Cliente Búnker (lectura)
    bunker_client = TelegramClient(bunker_session, api_id, api_hash)
    await bunker_client.connect()
    if not await bunker_client.is_user_authorized():
        print("Error: La sesión del Búnker no está autorizada. Asegúrate de que SESSION_BUNKER sea válida.")
        return

    # Cliente Producción (escritura)
    prod_client = TelegramClient(prod_session, api_id, api_hash)
    await prod_client.connect()
    if not await prod_client.is_user_authorized():
        print("Error: La sesión de Producción no está autorizada. Asegúrate de que SESSION_PROD sea válida.")
        return

    try:
        bunker_entity = await bunker_client.get_entity(bunker_channel_id)
        prod_entity = await prod_client.get_entity(prod_channel_id)
        
        found_message = None
        async for message in bunker_client.iter_messages(bunker_entity, search=search_query):
            # Buscar en el texto del mensaje
            if message.text and search_query.lower() in message.text.lower():
                found_message = message
                print(f"Mensaje encontrado en el Búnker (ID: {message.id}): {message.text[:50]}...")
                break # Encontramos el primero, es suficiente para esta petición
            # Buscar en el caption de la media si existe
            elif message.media:
                if hasattr(message.media, 'caption') and message.media.caption and search_query.lower() in message.media.caption.lower():
                    found_message = message
                    print(f"Mensaje con media encontrado en el Búnker (ID: {message.id}): {message.media.caption[:50]}...")
                    break

        if found_message:
            print(f"Reenviando el mensaje (ID: {found_message.id}) a '{prod_entity.title}' (ID: {prod_channel_id})...")
            await prod_client.forward_messages(prod_entity, found_message)
            print("Mensaje reenviado con éxito.")
        else:
            print(f"No se encontró ningún mensaje que contenga '{search_query}' en el Búnker de películas.")

    except Exception as e:
        print(f"Ocurrió un error: {e}")
    finally:
        await bunker_client.disconnect()
        await prod_client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
