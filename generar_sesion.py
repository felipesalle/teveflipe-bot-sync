"""
Script para generar tu TELEGRAM_STRING_SESSION.
Ejecuta este script una sola vez en tu terminal:
    python generar_sesion.py

Te pedirá tu número de teléfono (con código de país, ej: +52...) y el código de verificación de Telegram.
Al finalizar, imprimirá una cadena de texto larga. Esa cadena la guardarás en los Secrets de tu repositorio GitHub.
"""

import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = 28045969
API_HASH = "d8e515c5687943e5e0bf046f87c3d2cc"

async def main():
    print("=" * 60)
    print(" GENERADOR DE TELEGRAM_STRING_SESSION PARA GITHUB ACTIONS")
    print("=" * 60)
    
    async with TelegramClient(StringSession(), API_ID, API_HASH) as client:
        session_str = client.session.save()
        me = await client.get_me()
        print("\n✅ ¡Autenticación exitosa!")
        print(f"👤 Conectado como: {me.first_name} (@{me.username or 'sin_username'})")
        print("\n" + "=" * 60)
        print("COPIA LA SIGUIENTE LÍNEA COMPLETA (TELEGRAM_STRING_SESSION):")
        print("=" * 60)
        print(session_str)
        print("=" * 60)
        print("\nGuarda esta cadena en GitHub en:")
        print("Settings -> Secrets and variables -> Actions -> New repository secret")
        print("Nombre: TELEGRAM_STRING_SESSION")

if __name__ == "__main__":
    asyncio.run(main())
