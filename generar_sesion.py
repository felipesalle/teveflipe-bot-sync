"""
Script para generar y renovar TELEGRAM_STRING_SESSION.
Ejecuta este script en tu terminal:
    python generar_sesion.py

Te pedirá tu número de teléfono y el código de Telegram.
Al finalizar, actualizará automáticamente el secreto en GitHub y reanudará la sincronización.
"""

import asyncio
import subprocess
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = 28045969
API_HASH = "d8e515c5687943e5e0bf046f87c3d2cc"

async def main():
    print("=" * 60)
    print(" RENOVADOR DE TELEGRAM_STRING_SESSION PARA GITHUB ACTIONS")
    print("=" * 60)
    
    async with TelegramClient(StringSession(), API_ID, API_HASH) as client:
        session_str = client.session.save()
        me = await client.get_me()
        print("\n✅ ¡Autenticación exitosa!")
        print(f"👤 Conectado como: {me.first_name} (@{me.username or 'sin_username'})")
        print("\n" + "=" * 60)
        print("Actualizando automáticamente el secreto en GitHub...")
        
        try:
            res = subprocess.run(
                ["gh", "secret", "set", "TELEGRAM_STRING_SESSION", "--body", session_str],
                capture_output=True,
                text=True,
                shell=True
            )
            if res.returncode == 0:
                print("✅ Secreto 'TELEGRAM_STRING_SESSION' actualizado correctamente en GitHub.")
                print("🚀 Disparando la sincronización de Series Españolas...")
                sub_res = subprocess.run(
                    ["gh", "workflow", "run", "sync_espanolas.yml"],
                    capture_output=True,
                    text=True,
                    shell=True
                )
                if sub_res.returncode == 0:
                    print("✅ ¡Sincronización reanudada con éxito en GitHub Actions!")
                else:
                    print(f"⚠️ Aviso al disparar el workflow: {sub_res.stderr}")
            else:
                print(f"⚠️ No se pudo guardar con gh CLI: {res.stderr}")
                print("Por favor, copia esta cadena manualmente en GitHub Secrets:")
                print(session_str)
        except Exception as e:
            print(f"⚠️ Error actualizando secret: {e}")
            print("Copia la siguiente cadena manualmente:")
            print(session_str)

if __name__ == "__main__":
    asyncio.run(main())
