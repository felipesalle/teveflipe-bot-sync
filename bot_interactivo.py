import os
import sys
import json
import asyncio
import logging
import subprocess
import requests
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("BotInteractivo")

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
SESSION_PROD = os.getenv("SESSION_PROD", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
REPO_NAME = "felipesalle/teveflipe-bot-sync"

MAP_FILE = "canales_map.json"

def get_canales_summary() -> str:
    if not os.path.exists(MAP_FILE):
        return "❌ Archivo de canales no encontrado."
    with open(MAP_FILE, "r", encoding="utf-8") as f:
        canales = json.load(f)
    lines = ["📊 **ESTADO DE CANALES (BÚNKER ➔ PRODUCCIÓN):**\n"]
    for c in canales:
        estado = "🟢 Activo" if c.get("activo", True) else "⚪ Inactivo"
        tipo = "Foro" if c.get("is_forum") else "Canal"
        lines.append(f"• **{c['nombre']}** ({tipo})\n  ↳ Puntero: `{c.get('ultimo_id_sincronizado', 0)}` | {estado}")
    return "\n".join(lines)

def trigger_github_workflow(workflow_file: str) -> bool:
    # Intento 1: Vía gh CLI si está disponible localmente
    try:
        res = subprocess.run(["gh", "workflow", "run", workflow_file, "--repo", REPO_NAME],
                             capture_output=True, text=True, timeout=15)
        if res.returncode == 0:
            logger.info(f"Workflow '{workflow_file}' disparado exitosamente vía gh CLI.")
            return True
        logger.warning(f"gh CLI error: {res.stderr}")
    except Exception as e:
        logger.warning(f"Aviso ejecutando gh CLI: {e}")

    # Intento 2: Vía REST API de GitHub
    if GITHUB_TOKEN:
        try:
            url = f"https://api.github.com/repos/{REPO_NAME}/actions/workflows/{workflow_file}/dispatches"
            headers = {
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json"
            }
            res = requests.post(url, headers=headers, json={"ref": "main"}, timeout=10)
            if res.status_code in [200, 204]:
                logger.info(f"Workflow '{workflow_file}' disparado exitosamente vía API REST.")
                return True
        except Exception as e:
            logger.error(f"Error llamando API de GitHub: {e}")

    return False

def get_main_menu_buttons():
    return [
        [
            Button.inline("🔍 Escanear Búnkers", b"btn_escanear"),
            Button.inline("🚀 Sincronizar Todo", b"btn_sincronizar")
        ],
        [
            Button.inline("📦 Actualizar Inventario", b"btn_inventario"),
            Button.inline("📊 Ver Estado Canales", b"btn_estado")
        ]
    ]

async def main():
    logger.info("Iniciando Bot Interactivo de Sincronización TeVeFLIPE...")

    # Si hay token de bot se usa bot_token, sino se usa SESSION_PROD
    if BOT_TOKEN:
        bot = TelegramClient("bot_session", API_ID, API_HASH).start(bot_token=BOT_TOKEN)
    elif SESSION_PROD:
        bot = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)
        await bot.start()
    else:
        logger.error("❌ Se requiere TELEGRAM_BOT_TOKEN o SESSION_PROD.")
        sys.exit(1)

    me = await bot.get_me()
    logger.info(f"Bot activo como: {me.first_name} (@{getattr(me, 'username', 'N/A')})")

    @bot.on(events.NewMessage(pattern=r"^/(?:start|menu|ayuda)"))
    async def handler_start(event):
        text = (
            "🛰️ **Panel de Control: Sincronización Búnker ➔ Producción**\n\n"
            "Bienvenido. Desde aquí puedes escanear el contenido pendiente sin duplicados "
            "y lanzar la sincronización segura hacia los canales y supergrupos de TeVeFLIPE.\n\n"
            "Selecciona una opción:"
        )
        await event.respond(text, buttons=get_main_menu_buttons())

    @bot.on(events.NewMessage(pattern=r"^/estado"))
    async def handler_estado(event):
        msg = get_canales_summary()
        await event.respond(msg, buttons=get_main_menu_buttons())

    @bot.on(events.NewMessage(pattern=r"^/escanear"))
    async def handler_escanear(event):
        status_msg = await event.respond("⏳ Disparando auditoría anti-duplicados en GitHub Actions...")
        ok = trigger_github_workflow("auditar_novedades.yml")
        if ok:
            await status_msg.edit(
                "✅ **Auditoría iniciada en GitHub Actions.**\n"
                "El informe limpio aparecerá en breves momentos en los registros de la acción o en la Comunidad.",
                buttons=get_main_menu_buttons()
            )
        else:
            await status_msg.edit(
                "⚠️ No se pudo disparar el workflow automáticamente. Revisa las credenciales de GitHub.",
                buttons=get_main_menu_buttons()
            )

    @bot.on(events.NewMessage(pattern=r"^/sincronizar"))
    async def handler_sincronizar(event):
        status_msg = await event.respond("⏳ Iniciando sincronización universal Búnker ➔ Producción...")
        ok = trigger_github_workflow("sync_novedades.yml")
        if ok:
            await status_msg.edit(
                "🚀 **Sincronización lanzada con éxito.**\n"
                "Los archivos están siendo clonados por Relay privado y se publicarán las fichas TMDB con carátula.",
                buttons=get_main_menu_buttons()
            )
        else:
            await status_msg.edit(
                "⚠️ No se pudo disparar el workflow de sincronización.",
                buttons=get_main_menu_buttons()
            )

    @bot.on(events.CallbackQuery)
    async def callback_handler(event):
        data = event.data
        if data == b"btn_escanear":
            await event.answer("Iniciando escáner...")
            ok = trigger_github_workflow("auditar_novedades.yml")
            resp = "✅ **Escáner lanzado en GitHub Actions.**" if ok else "⚠️ Error al disparar escáner."
            await event.respond(resp, buttons=get_main_menu_buttons())

        elif data == b"btn_sincronizar":
            await event.answer("Iniciando sincronización...")
            ok = trigger_github_workflow("sync_novedades.yml")
            resp = "🚀 **Sincronización en curso en GitHub Actions.**" if ok else "⚠️ Error al disparar sincronización."
            await event.respond(resp, buttons=get_main_menu_buttons())

        elif data == b"btn_inventario":
            await event.answer("Actualizando inventario...")
            ok = trigger_github_workflow("actualizar_inventario.yml")
            resp = "📦 **Actualización de inventario lanzada en GitHub Actions.**" if ok else "⚠️ Error al disparar tarea."
            await event.respond(resp, buttons=get_main_menu_buttons())

        elif data == b"btn_estado":
            await event.answer()
            msg = get_canales_summary()
            await event.respond(msg, buttons=get_main_menu_buttons())

    logger.info("Bot en escucha de eventos...")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
