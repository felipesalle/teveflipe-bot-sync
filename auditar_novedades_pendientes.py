import os
import sys
import json
import asyncio
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s"
)
logger = logging.getLogger("AuditoriaNovedades")

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_BUNKER = os.getenv("SESSION_BUNKER") or ""
SESSION_PROD = os.getenv("SESSION_PROD") or ""
MAP_FILE = "canales_map.json"

VIDEO_EXTS = ('.mp4', '.mkv', '.avi', '.mov', '.ts', '.m4v', '.wmv', '.flv', '.webm', '.rar', '.7z')

def get_file_info(msg):
    fn = ""
    sz = 0
    if msg.file:
        fn = getattr(msg.file, 'name', '') or ""
        sz = getattr(msg.file, 'size', 0) or 0
    
    txt = (msg.message or "").strip()
    title = fn
    if not title:
        first_line = txt.split('\n')[0].strip() if txt else ""
        title = first_line[:80] if first_line else f"Mensaje {msg.id}"
        
    size_mb = f"{sz / (1024*1024):.1f} MB" if sz > 0 else ""
    return title, fn, size_mb

async def main():
    print("=" * 70)
    print("🔍 AUDITORÍA DE NOVEDADES EN BÚNKERS (SOLO LECTURA)")
    print("=" * 70)

    if not SESSION_BUNKER and not SESSION_PROD:
        logger.error("❌ ERROR: Ni SESSION_BUNKER ni SESSION_PROD configuradas.")
        sys.exit(1)

    # Usamos SESSION_BUNKER prioritariamente para leer búnkers
    sess_reader = SESSION_BUNKER or SESSION_PROD
    client = TelegramClient(StringSession(sess_reader), API_ID, API_HASH)
    await client.start()
    
    me = await client.get_me()
    logger.info(f"Conectado como: {me.first_name} (ID: {me.id})")
    
    logger.info("Cargando lista de diálogos...")
    try:
        await client.get_dialogs(limit=None)
    except Exception as e:
        logger.warning(f"Aviso al cargar diálogos: {e}")

    # Cliente prod opcional para verificar si ya existe en producción
    client_prod = None
    if SESSION_PROD and SESSION_PROD != sess_reader:
        try:
            client_prod = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)
            await client_prod.start()
            await client_prod.get_dialogs(limit=None)
        except Exception as e:
            logger.warning(f"No se pudo iniciar cliente de verificación de prod: {e}")
            client_prod = None

    if not os.path.exists(MAP_FILE):
        logger.error(f"❌ No se encontró {MAP_FILE}.")
        await client.disconnect()
        return

    with open(MAP_FILE, "r", encoding="utf-8") as f:
        canales = json.load(f)

    reporte_canales = []

    for c in canales:
        if not c.get("activo", True):
            continue
            
        c_nombre = c["nombre"]
        b_id = c.get("bunker_id")
        p_id = c.get("produccion_id")
        last_id = c.get("ultimo_id_sincronizado", 0)
        topic_id = c.get("topic_id")
        is_forum = c.get("is_forum", False)

        if not b_id:
            continue

        try:
            try:
                ent_bunker = await client.get_input_entity(b_id)
            except Exception:
                ent_bunker = await client.get_entity(b_id)

            if topic_id:
                latest = await client.get_messages(ent_bunker, reply_to=topic_id, limit=1)
            else:
                latest = await client.get_messages(ent_bunker, limit=1)

            current_top = latest[0].id if latest else 0

            if current_top <= last_id:
                reporte_canales.append({
                    "nombre": c_nombre,
                    "estado": "AL_DIA",
                    "last_id": last_id,
                    "current_top": current_top,
                    "archivos": []
                })
                continue

            # Hay mensajes nuevos
            iter_kwargs = {"min_id": last_id, "reverse": True}
            if topic_id:
                iter_kwargs["reply_to"] = topic_id

            new_msgs = [m async for m in client.iter_messages(ent_bunker, **iter_kwargs)
                        if not m.action and (m.media or m.text)]

            archivos_detectados = []
            for m in new_msgs:
                title, fn, size_mb = get_file_info(m)
                archivos_detectados.append({
                    "msg_id": m.id,
                    "titulo": title,
                    "filename": fn,
                    "size": size_mb,
                    "es_media": bool(m.media)
                })

            reporte_canales.append({
                "nombre": c_nombre,
                "estado": "NOVEDADES",
                "last_id": last_id,
                "current_top": current_top,
                "archivos": archivos_detectados
            })

        except Exception as e:
            reporte_canales.append({
                "nombre": c_nombre,
                "estado": "ERROR",
                "error": str(e),
                "last_id": last_id,
                "archivos": []
            })

    print("\n" + "=" * 70)
    print("📋 RESULTADOS DE LA AUDITORÍA DE CANALES BÚNKER")
    print("=" * 70)

    con_novedades = [r for r in reporte_canales if r["estado"] == "NOVEDADES"]
    al_dia = [r for r in reporte_canales if r["estado"] == "AL_DIA"]
    con_error = [r for r in reporte_canales if r["estado"] == "ERROR"]

    if con_novedades:
        print(f"\n🔔 SE ENCONTRARON NOVEDADES EN {len(con_novedades)} CANALES:\n")
        for r in con_novedades:
            print(f"📁 {r['nombre']} (Puntero: {r['last_id']} ➔ Búnker: {r['current_top']})")
            print(f"   Total mensajes nuevos: {len(r['archivos'])}")
            for arch in r["archivos"]:
                sz_str = f" [{arch['size']}]" if arch['size'] else ""
                tipo_str = "🎬" if arch['es_media'] else "📝"
                print(f"   ↳ {tipo_str} [ID {arch['msg_id']}] {arch['titulo']}{sz_str}")
            print()
    else:
        print("\n✨ ¡Todos los canales sincronizables están al día!")

    if al_dia:
        print(f"👌 Canales al día ({len(al_dia)}):")
        for r in al_dia:
            print(f"   • {r['nombre']} (ID: {r['last_id']})")
        print()

    if con_error:
        print(f"⚠️ Canales con aviso de acceso ({len(con_error)}):")
        for r in con_error:
            print(f"   • {r['nombre']}: {r.get('error', 'Error desconocido')}")
        print()

    await client.disconnect()
    if client_prod:
        await client_prod.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
