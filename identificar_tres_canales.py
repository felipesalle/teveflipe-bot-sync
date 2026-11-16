import os
import sys
import json
import asyncio
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s")
logger = logging.getLogger("IdentificarCanales")

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_BUNKER = os.getenv("SESSION_BUNKER") or ""
SESSION_PROD = os.getenv("SESSION_PROD") or ""

TARGET_KEYS = [
    "4420612937",
    "4450378925",
    "4457839581"
]

async def main():
    session_str = SESSION_BUNKER or SESSION_PROD
    if not session_str:
        logger.error("No hay sesiones.")
        return

    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        logger.error("No autorizado.")
        await client.disconnect()
        return

    me = await client.get_me()
    logger.info(f"Conectado como: {me.first_name} (ID: {me.id})")

    found_channels = {}

    logger.info("Escaneando diálogos del usuario...")
    async for d in client.iter_dialogs(limit=500):
        s_id = str(d.id)
        abs_id = str(abs(d.id))
        d_name = d.name or ""
        
        for k in TARGET_KEYS:
            if k in s_id or k in abs_id:
                found_channels[k] = {
                    "key": k,
                    "id": d.id,
                    "name": d_name,
                    "is_channel": d.is_channel,
                    "is_group": d.is_group,
                    "is_forum": getattr(d.entity, 'forum', False),
                    "entity_type": type(d.entity).__name__
                }
                logger.info(f"✅ Encontrado para clave '{k}': '{d_name}' (ID: {d.id}, Forum={found_channels[k]['is_forum']})")

    # Si alguno no se encontró en dialogs, intentar get_entity directo
    for k in TARGET_KEYS:
        if k not in found_channels:
            candidates = [int(f"-100{k}"), int(f"-{k}"), int(k)]
            for cid in candidates:
                try:
                    ent = await client.get_entity(cid)
                    found_channels[k] = {
                        "key": k,
                        "id": ent.id,
                        "name": getattr(ent, 'title', str(cid)),
                        "is_forum": getattr(ent, 'forum', False),
                        "entity_type": type(ent).__name__
                    }
                    logger.info(f"✅ Encontrado vía get_entity({cid}): '{found_channels[k]['name']}'")
                    break
                except Exception as e:
                    pass

    print("\n" + "="*80)
    print("CANALES IDENTIFICADOS:")
    print("="*80)
    for k, v in found_channels.items():
        print(f"Clave: {k} -> ID: {v['id']} | Nombre: '{v['name']}' | Es Foro/Temas: {v.get('is_forum')}")
    print("="*80)

    with open("canales_identificados.json", "w", encoding="utf-8") as f:
        json.dump(found_channels, f, ensure_ascii=False, indent=2)

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
