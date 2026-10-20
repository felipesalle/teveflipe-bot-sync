import asyncio
import os
import re
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
TELEGRAM_STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION", "")
SESSION_PROD = os.getenv("SESSION_PROD", "")
SESSION_BUNKER = os.getenv("SESSION_BUNKER", "")

TARGETS = [
    {
        "id": "leftovers",
        "name": "The Leftovers",
        "queries": [
            "The Leftovers", "Leftovers", "Leftovers 2x10", "Leftovers S02E10", 
            "Leftovers 3x08", "Leftovers S03E08", "Leftovers 1x01", "Leftovers S01E01"
        ]
    },
    {
        "id": "dark",
        "name": "Dark",
        "queries": [
            "Dark S01", "Dark S02", "Dark S03", "Dark 3x01", "Dark 3x08", 
            "Dark Temporada 3", "Dark Netflix", "Dark 1080p", "Dark 720p"
        ]
    },
    {
        "id": "americans",
        "name": "The Americans",
        "queries": [
            "The Americans", "The Americans S01", "The Americans 1x01", "The Americans 1x09",
            "The Americans 1080p", "The Americans 720p"
        ]
    },
    {
        "id": "bear",
        "name": "The Bear",
        "queries": [
            "The Bear S01", "The Bear S02", "The Bear S03", "The Bear 1x01", 
            "The Bear 2x10", "The Bear S02E10", "The Bear 1080p", "The Bear 720p"
        ]
    },
    {
        "id": "stranger_things",
        "name": "Stranger Things",
        "queries": [
            "Stranger Things S01", "Stranger Things S02", "Stranger Things S03", "Stranger Things S04",
            "Stranger Things 1x01", "Stranger Things 1080p", "Stranger Things 720p"
        ]
    }
]

async def inspect_client(session_str, session_name):
    if not session_str:
        print(f"[{session_name}] Sesión vacía, omitiendo.")
        return
    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        print(f"[{session_name}] No autorizado.")
        await client.disconnect()
        return

    me = await client.get_me()
    print(f"\n=======================================================")
    print(f"[{session_name}] Conectado como: {me.first_name} (ID: {me.id})")
    print(f"=======================================================")

    dialogs = []
    async for d in client.iter_dialogs(limit=100):
        if d.is_channel or d.is_group:
            dialogs.append(d)
            print(f"  📁 Chat: {d.title} (ID: {d.id})")

    # Para cada target, buscar en cada diálogo
    for target in TARGETS:
        print(f"\n-------------------------------------------------------")
        print(f"🔍 [{session_name}] BUSCANDO: {target['name']}")
        print(f"-------------------------------------------------------")
        for d in dialogs:
            # Buscar cada query
            found_msgs = {}
            for q in target["queries"]:
                try:
                    async for m in client.iter_messages(d.entity, search=q, limit=20):
                        if m.file:
                            fn = getattr(m.file, 'name', '') or ''
                            ext = os.path.splitext(fn)[1].lower()
                            if fn and m.id not in found_msgs:
                                found_msgs[m.id] = (fn, ext, m.file.size)
                except Exception as ex:
                    # algunos canales pueden dar error de búsqueda
                    pass

            if found_msgs:
                print(f"  👉 En '{d.title}' ({d.id}): {len(found_msgs)} archivos encontrados:")
                # Filtrar solo mkv / mp4 vs rar / zip
                mkv_mp4 = [v for k, v in found_msgs.items() if v[1] in ['.mkv', '.mp4']]
                compressed = [v for k, v in found_msgs.items() if v[1] in ['.rar', '.zip', '.z01', '.part1', '.part2']]
                print(f"     * Reproducibles (.mkv/.mp4): {len(mkv_mp4)}")
                for fn, ext, sz in mkv_mp4[:10]:
                    print(f"       - {fn} ({sz // (1024*1024)} MB)")
                if len(mkv_mp4) > 10:
                    print(f"       ... y {len(mkv_mp4)-10} más reproducibles.")
                if compressed:
                    print(f"     * Comprimidos/Rar/Zip: {len(compressed)}")
                    for fn, ext, sz in compressed[:5]:
                        print(f"       - {fn}")

    await client.disconnect()

async def main():
    print("🚀 INICIANDO BÚSQUEDA PROFUNDA EN TODAS LAS CUENTAS Y DIÁLOGOS...")
    await inspect_client(SESSION_PROD, "PROD")
    await inspect_client(TELEGRAM_STRING_SESSION, "COMMUNITY")
    await inspect_client(SESSION_BUNKER, "BUNKER")

if __name__ == "__main__":
    asyncio.run(main())
