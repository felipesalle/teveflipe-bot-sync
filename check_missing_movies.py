import asyncio
import os
from telethon.sync import TelegramClient
from telethon.tl.types import Document, Video, MessageMediaDocument, MessageMediaVideo

# --- Configuration ---
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
SESSION_BUNKER = os.getenv('SESSION_BUNKER')
SESSION_PROD = os.getenv('SESSION_PROD')

# Channel IDs from the provided map
BUNKER_PELICULAS_ESTRENOS_ID = -1002146236969 # 🏆 Películas Estrenos - TeVeFLIPE (Búnker)
PROD_PELICULAS_ESTRENOS_ID = -1003763464899 # 🏆 Películas Estrenos - TeVeFLIPE (Producción)

async def get_media_identifiers(client, channel_id):
    """
    Fetches unique identifiers (file_name, file_size) for media messages
    in a given channel.
    """
    media_identifiers = set()
    print(f"[{client.session.filename}] Fetching media identifiers from channel ID: {channel_id}...")
    try:
        async for message in client.iter_messages(channel_id, limit=None): # limit=None to get all messages
            if message.media:
                file_name = None
                file_size = None

                if isinstance(message.media, MessageMediaDocument) and isinstance(message.media.document, Document):
                    doc = message.media.document
                    file_size = doc.size
                    for attr in doc.attributes:
                        if hasattr(attr, 'file_name'):
                            file_name = attr.file_name
                            break
                elif isinstance(message.media, MessageMediaVideo) and isinstance(message.media.video, Video):
                    video = message.media.video
                    file_size = video.size
                    for attr in video.attributes:
                        if hasattr(attr, 'file_name'):
                            file_name = attr.file_name
                            break
                
                if file_name and file_size:
                    media_identifiers.add((file_name, file_size))
    except Exception as e:
        print(f"Error fetching messages from channel {channel_id}: {e}")
    print(f"[{client.session.filename}] Found {len(media_identifiers)} unique media identifiers in channel ID: {channel_id}.")
    return media_identifiers

async def main():
    if not all([API_ID, API_HASH, SESSION_BUNKER, SESSION_PROD]):
        print("Error: TELEGRAM_API_ID, TELEGRAM_API_HASH, SESSION_BUNKER, or SESSION_PROD environment variables are not set.")
        return

    print("Initializing Telegram clients...")
    bunker_client = TelegramClient(SESSION_BUNKER, API_ID, API_HASH)
    prod_client = TelegramClient(SESSION_PROD, API_ID, API_HASH)

    try:
        print("Connecting Bunker client...")
        await bunker_client.connect()
        if not await bunker_client.is_user_authorized():
            print("Bunker client not authorized. Please ensure SESSION_BUNKER is valid.")
            return

        print("Connecting Production client...")
        await prod_client.connect()
        if not await prod_client.is_user_authorized():
            print("Production client not authorized. Please ensure SESSION_PROD is valid.")
            return

        print("Fetching media identifiers from Production channel (Peliculas Estrenos)...")
        prod_media_identifiers = await get_media_identifiers(prod_client, PROD_PELICULAS_ESTRENOS_ID)

        print("Checking Bunker channel (Repositorio de Peliculas) for missing movies in Production...")
        missing_movies_count = 0
        
        # Iterate through Bunker messages to find missing ones
        async for message in bunker_client.iter_messages(BUNKER_PELICULAS_ESTRENOS_ID, limit=None):
            if message.media:
                file_name = None
                file_size = None

                if isinstance(message.media, MessageMediaDocument) and isinstance(message.media.document, Document):
                    doc = message.media.document
                    file_size = doc.size
                    for attr in doc.attributes:
                        if hasattr(attr, 'file_name'):
                            file_name = attr.file_name
                            break
                elif isinstance(message.media, MessageMediaVideo) and isinstance(message.media.video, Video):
                    video = message.media.video
                    file_size = video.size
                    for attr in video.attributes:
                        if hasattr(attr, 'file_name'):
                            file_name = attr.file_name
                            break
                
                if file_name and file_size:
                    if (file_name, file_size) not in prod_media_identifiers:
                        missing_movies_count += 1
                        print(f"\n--- Missing Movie Found ---")
                        print(f"Bunker Message ID: {message.id}")
                        print(f"File Name: {file_name}")
                        print(f"File Size: {file_size} bytes")
                        if message.caption:
                            print(f"Caption: {message.caption[:100]}...") # Print first 100 chars of caption
                        else:
                            print("Caption: N/A")
                        # Construct a public link for the bunker message. Note: -100 is removed for public channel links.
                        # For private channels, this link might only work if the user is a member.
                        print(f"Link to Bunker message: https://t.me/c/{str(BUNKER_PELICULAS_ESTRENOS_ID).replace('-100', '')}/{message.id}")
        
        if missing_movies_count == 0:
            print("\nNo missing movies found in 'Repositorio de Peliculas' that are not in 'Peliculas Estrenos'.")
        else:
            print(f"\nTotal missing movies found: {missing_movies_count}")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        print("Disconnecting clients...")
        await bunker_client.disconnect()
        await prod_client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
