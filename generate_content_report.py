import os
import asyncio
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

# --- Configuración de Canales Búnker ---
# Mapeo de nombres de canales a sus IDs de Búnker y Topic IDs (si aplica)
# Usamos 'None' para topic_id si el canal no es un supergrupo con temas o si queremos contar todo el canal.
BUNKER_CHANNELS = {
    "🎬 Películas Estrenos - TeVeFLIPE": {"id": -1002146236969, "topic": None},
    "📺 Series TV - TeVeFLIPE": {"id": -1002097175258, "topic": None},
    "🇪🇸 Series Españolas - TeVeFLIPE": {"id": -1002160549536, "topic": 21},
    "🎞️ Películas Clásicas - TeVeFLIPE": {"id": -1004388643765, "topic": None},
    "📼 Cine de los 80 y 90 - TeVeFLIPE": {"id": -1004316187715, "topic": None},
    "🎬 Películas Infantiles - TeVeFLIPE": {"id": -1004383923903, "topic": None},
    "👶 Series Infantiles - TeVeFLIPE": {"id": -1004385066808, "topic": None},
    "⛩️ Películas Anime - TeVeFLIPE": {"id": -1004440781202, "topic": None},
    "💥 Series Anime - TeVeFLIPE": {"id": -1004445501873, "topic": None},
    "🥢 Series Asiáticas & Doramas - TeVeFLIPE": {"id": -1004488255668, "topic": None},
    "✨ Series Turcas y Telenovelas - TeVeFLIPE": {"id": -1002160549536, "topic": 5},
    "📺 Series Retro y Clásicas - TeVeFLIPE": {"id": -1003971365582, "topic": None},
    "🌍 Documentales - TeVeFLIPE": {"id": -1001905652210, "topic": 11},
    "🎸 Conciertos & Música - TeVeFLIPE": {"id": -1003567099600, "topic": 20},
    "🪐 Sagas & Franquicias - TeVeFLIPE": {"id": -1003913363596, "topic": None}
}

async def main():
    # Credenciales de Telegram desde variables de entorno
    api_id = os.environ.get('TELEGRAM_API_ID')
    api_hash = os.environ.get('TELEGRAM_API_HASH')
    session_bunker = os.environ.get('SESSION_BUNKER')

    if not all([api_id, api_hash, session_bunker]):
        print("Error: Asegúrate de que las variables de entorno TELEGRAM_API_ID, TELEGRAM_API_HASH y SESSION_BUNKER estén configuradas.")
        return

    try:
        api_id = int(api_id)
    except ValueError:
        print("Error: TELEGRAM_API_ID debe ser un número entero.")
        return

    print("Iniciando conexión con la cuenta Búnker...")
    client = TelegramClient(session_bunker, api_id, api_hash)

    try:
        await client.connect()
        if not await client.is_user_authorized():
            print("Error: La sesión Búnker no está autorizada. Por favor, asegúrate de que SESSION_BUNKER sea válida.")
            # En un entorno de GitHub Actions, esto significa que el secret SESSION_BUNKER está mal o caducado.
            return

        print("Conexión exitosa. Generando informe de contenido...")
        report_data = []
        total_cubatas = 0

        for channel_name, config in BUNKER_CHANNELS.items():
            bunker_id = config["id"]
            topic_id = config["topic"]
            
            try:
                # Usamos get_messages con limit=0 para obtener el total de mensajes de forma eficiente.
                # Si hay un topic_id, lo pasamos para contar solo los mensajes de ese tema.
                messages = await client.get_messages(bunker_id, limit=0, reply_to=topic_id)
                count = messages.total
                report_data.append(f"- {channel_name} (ID: {bunker_id}{f', Topic: {topic_id}' if topic_id else ''}): {count} cubatas")
                total_cubatas += count
                print(f"Contado: {channel_name} -> {count} cubatas")
            except Exception as e:
                report_data.append(f"- {channel_name} (ID: {bunker_id}{f', Topic: {topic_id}' if topic_id else ''}): Error al contar ({e})")
                print(f"Error al contar {channel_name}: {e}")

        print("\n--- Informe de Contenido TeVeFLIPE (Cubatas) ---")
        for item in report_data:
            print(item)
        print(f"\nTotal general de cubatas en el Búnker: {total_cubatas}")
        print("--------------------------------------------------")

    except SessionPasswordNeededError:
        print("Error: Se requiere una contraseña para la sesión. Asegúrate de que tu sesión no esté protegida por 2FA o que el secret SESSION_BUNKER incluya la contraseña si es necesario.")
    except Exception as e:
        print(f"Ocurrió un error inesperado: {e}")
    finally:
        if client.is_connected():
            await client.disconnect()
            print("Desconectado de Telegram.")

if __name__ == '__main__':
    asyncio.run(main())
