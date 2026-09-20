#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
preparar_supergrupos_series.py
Crea o localiza los 4 Supergrupos privados con soporte de Foros/Temas en Telegram
y exporta sus enlaces permanentes para registrarlos en admin.html.
"""

import os
import sys
import json
import asyncio
import logging
from telethon import TelegramClient, utils
from telethon.sessions import StringSession
from telethon.tl.functions.channels import CreateChannelRequest, ToggleForumRequest
from telethon.tl.functions.messages import ExportChatInviteRequest
from telethon.tl.types import ChatInviteExported

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("PrepararSupergrupos")

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION = os.environ["TELEGRAM_STRING_SESSION"]

OUTPUT_CONFIG = "config_supergrupos_series.json"

GRUPOS_A_CONFIGURAR = [
    {
        "key": "turcas_y_telenovelas",
        "title": "📺 Series Turcas y Telenovelas - TeveFlipe",
        "about": "Catálogo de Series Turcas, Telenovelas y producciones latinas para TeveFlipe.",
        "search_keywords": ["turcas", "telenovelas"],
        "category": "telenovela"
    },
    {
        "key": "espanolas",
        "title": "📺 Series Españolas - TeveFlipe",
        "about": "Catálogo de Series Españolas organizadas por Temas para TeveFlipe.",
        "search_keywords": ["españolas", "series españolas"],
        "category": "serie"
    },
    {
        "key": "retro_clasicas",
        "title": "📺 Series Retro y Clásicas - TeveFlipe",
        "about": "Catálogo de Series Retro y Clásicas anteriores a 2010 para TeveFlipe.",
        "search_keywords": ["retro", "clásicas", "clasicas"],
        "category": "serie"
    },
    {
        "key": "internacionales",
        "title": "📺 Series TV - TeveFlipe",
        "about": "Catálogo de Series Internacionales Modernas organizadas por Temas para TeveFlipe.",
        "search_keywords": ["series tv - teveflipe", "series tv"],
        "category": "serie"
    }
]


async def main():
    logger.info("=" * 65)
    logger.info("🛠️ CONFIGURACIÓN DE LOS 4 SUPERGRUPOS PRIVADOS CON FOROS")
    logger.info("=" * 65)

    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        me = await client.get_me()
        logger.info(f"Conectado como: {me.first_name} [ID: {me.id}]")

        # Cargar configuración previa si existe
        config = {}
        if os.path.exists(OUTPUT_CONFIG):
            try:
                with open(OUTPUT_CONFIG, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except Exception:
                config = {}

        # Listar diálogos existentes
        dialogs = []
        async for d in client.iter_dialogs(limit=150):
            if d.is_channel or d.is_group:
                dialogs.append(d)

        resultados = {}

        for ginfo in GRUPOS_A_CONFIGURAR:
            key = ginfo["key"]
            title = ginfo["title"]
            about = ginfo["about"]
            cat = ginfo["category"]
            search_kws = ginfo["search_keywords"]

            chat_obj = None
            chat_id = config.get(key, {}).get("id")

            # 1. Probar por ID previo
            if chat_id:
                try:
                    chat_obj = await client.get_entity(chat_id)
                    logger.info(f"✅ Encontrado por ID guardado: {title} ({chat_id})")
                except Exception:
                    chat_obj = None

            # 2. Buscar en diálogos existentes donde el usuario sea creador o administrador
            if not chat_obj:
                for d in dialogs:
                    is_admin = getattr(d.entity, 'creator', False) or getattr(d.entity, 'admin_rights', None)
                    if not is_admin:
                        continue
                    d_title = d.title.lower()
                    if any(kw in d_title for kw in search_kws):
                        chat_obj = d.entity
                        chat_id = utils.get_peer_id(chat_obj)
                        logger.info(f"✅ Encontrado en diálogos existentes propios: '{d.title}' [ID: {chat_id}]")
                        break

            # 3. Si no existe, crear el Supergrupo privado
            if not chat_obj:
                logger.info(f"🚀 Creando nuevo Supergrupo privado: '{title}'...")
                res = await client(CreateChannelRequest(
                    title=title,
                    about=about,
                    broadcast=False,
                    megagroup=True,
                    forum=True
                ))
                chat_obj = res.chats[0]
                chat_id = utils.get_peer_id(chat_obj)
                logger.info(f"🎉 Creado con éxito: '{title}' [ID: {chat_id}]")

            # 4. Asegurar que Foros/Temas esté activo
            try:
                await client(ToggleForumRequest(channel=chat_obj, enabled=True, tabs=False))
                logger.info(f"✨ Foros/Temas habilitados en '{title}'.")
            except Exception as e:
                logger.debug(f"Aviso en ToggleForum: {e}")

            # 5. Exportar enlace permanente de invitación
            invite_link = config.get(key, {}).get("invite_link", "")
            try:
                exported = await client(ExportChatInviteRequest(
                    peer=chat_obj,
                    title=f"Enlace TeveFlipe {title}"
                ))
                if isinstance(exported, ChatInviteExported):
                    invite_link = exported.link
                    logger.info(f"🔗 Enlace de invitación: {invite_link}")
            except Exception as e:
                logger.warning(f"Aviso al exportar enlace para '{title}': {e}")

            resultados[key] = {
                "id": chat_id,
                "title": title,
                "category": cat,
                "is_forum": True,
                "invite_link": invite_link
            }

        # Guardar archivo de configuración
        with open(OUTPUT_CONFIG, "w", encoding="utf-8") as f:
            json.dump(resultados, f, indent=2, ensure_ascii=False)

        logger.info("=" * 65)
        logger.info("📋 RESUMEN DE LOS 4 SUPERGRUPOS CONFIGURADOS:")
        print(json.dumps(resultados, indent=2, ensure_ascii=False))
        logger.info("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
