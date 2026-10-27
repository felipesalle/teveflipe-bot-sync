import asyncio
import os
import logging
from telethon import TelegramClient

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def check_telegram_connection():
    api_id = os.getenv('TELEGRAM_API_ID')
    api_hash = os.getenv('TELEGRAM_API_HASH')
    string_session = os.getenv('TELEGRAM_STRING_SESSION')

    if not all([api_id, api_hash, string_session]):
        logger.error("Missing one or more Telegram secrets (TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_STRING_SESSION).")
        return

    logger.info("Attempting to connect to Telegram...")
    # Telethon expects API ID as int
    client = TelegramClient(string_session, int(api_id), api_hash)

    try:
        await client.connect()
        if not await client.is_user_authorized():
            logger.error("Client is not authorized. The string session might be invalid or expired.")
            logger.info("Please ensure TELEGRAM_STRING_SESSION is correctly set and valid in GitHub secrets.")
            return

        me = await client.get_me()
        logger.info("Successfully connected to Telegram!")
        logger.info(f"Connected as: {me.first_name} {me.last_name or ''} (@{me.username})")
        logger.info(f"User ID: {me.id}")
        logger.info(f"Phone: {me.phone or 'N/A'}")
        logger.info(f"Is bot: {me.bot}")

    except Exception as e:
        logger.error(f"An error occurred during Telegram connection: {e}", exc_info=True)
    finally:
        if client.is_connected():
            await client.disconnect()
            logger.info("Disconnected from Telegram.")

if __name__ == '__main__':
    asyncio.run(check_telegram_connection())
