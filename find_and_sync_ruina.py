import asyncio
import os
import re
import sys
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaDocument, DocumentAttributeFilename, DocumentAttributeVideo

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_BUNKER = os.getenv("SESSION_BUNKER", "")
SESSION_PROD = os.getenv("SESSION_PROD", "")

BUNKER_80_90 = -1004316187715
PROD_80_90 = -1004467288762
COMUNIDAD_CASTELLANA = -1001905652210
REPOSITORIO_PELIS = -1002146236969
PELIS_CLASICAS = -1004388643765

def get_filename(msg):
    if not msg or not msg.media:
        return ""
    if getattr(msg, "file", None) and getattr(msg.file, "name", None):
        return msg.file.name or ""
    if isinstance(msg.media, MessageMediaDocument) and msg.media.document:
        for attr in msg.media.document.attributes:
            if isinstance(attr, DocumentAttributeFilename):
                return attr.file_name or ""
    return ""

def format_size(size_bytes):
    if not size_bytes:
        return "0 MB"
    mb = size_bytes / (1024 * 1024)
    if mb > 1024:
        return f"{mb / 1024:.2f} GB"
    return f"{mb:.1f} MB"

async def main():
    if not SESSION_BUNKER:
        print("ERROR: SESSION_BUNKER no encontrada")
        sys.exit(1)
    if not SESSION_PROD:
        print("ERROR: SESSION_PROD no encontrada")
        sys.exit(1)

    print("=== Conectando clientes Telegram ===")
    bunker_client = TelegramClient(StringSession(SESSION_BUNKER), API_ID, API_HASH)
    prod_client = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)

    await bunker_client.start()
    await prod_client.start()

    me_b = await bunker_client.get_me()
    me_p = await prod_client.get_me()
    print(f"Bunker conectado como: {me_b.first_name} ({me_b.id})")
    print(f"Producción conectado como: {me_p.first_name} ({me_p.id})")

    # 1. Inspeccionar versión existente en Producción y Bunker 80 y 90
    print("\n--- 1. Revisando versión existente en Cine 80 y 90 ---")
    prod_existing = []
    try:
        prod_entity = await prod_client.get_entity(PROD_80_90)
        async for msg in prod_client.iter_messages(prod_entity, search="ruina"):
            fname = get_filename(msg)
            print(f"En Producción: Msg ID {msg.id} | Archivo: {fname} | Texto: {repr(msg.text[:60] if msg.text else '')}")
            prod_existing.append(msg)
    except Exception as e:
        print(f"Aviso revisando Producción: {e}")

    bunker_existing = []
    try:
        bunker_entity = await bunker_client.get_entity(BUNKER_80_90)
        async for msg in bunker_client.iter_messages(bunker_entity, search="ruina"):
            fname = get_filename(msg)
            print(f"En Bunker: Msg ID {msg.id} | Archivo: {fname} | Texto: {repr(msg.text[:60] if msg.text else '')}")
            bunker_existing.append(msg)
    except Exception as e:
        print(f"Aviso revisando Bunker: {e}")

    # 2. Búsqueda exhaustiva en Comunidad Castellana (-1001905652210)
    print("\n--- 2. Buscando en Comunidad Castellana (-1001905652210) ---")
    candidates = []
    search_queries = ["Esta casa es una ruina", "casa es una ruina", "money pit"]

    search_targets = [
        ("Comunidad Castellana", COMUNIDAD_CASTELLANA),
        ("Repositorio Películas", REPOSITORIO_PELIS),
        ("Películas Clásicas", PELIS_CLASICAS)
    ]

    seen_msg_keys = set()

    for chat_label, chat_id in search_targets:
        print(f"\nBuscando en {chat_label} ({chat_id})...")
        try:
            target_entity = await bunker_client.get_entity(chat_id)
        except Exception as e:
            print(f"No se pudo acceder a {chat_label}: {e}")
            continue

        for q in search_queries:
            try:
                async for msg in bunker_client.iter_messages(target_entity, search=q, limit=50):
                    if not msg.media:
                        continue
                    key = (chat_id, msg.id)
                    if key in seen_msg_keys:
                        continue
                    seen_msg_keys.add(key)

                    fname = get_filename(msg)
                    fname_lower = fname.lower()
                    caption = msg.text or ""

                    # Excluir archivos no permitidos
                    if fname_lower.endswith((".rar", ".zip", ".7z", ".avi", ".txt", ".srt")):
                        print(f"  [Ignorado - Formato no admitido] Msg {msg.id}: {fname}")
                        continue

                    if not fname_lower.endswith((".mp4", ".mkv")):
                        # Verificar si es video de Telegram
                        if not getattr(msg, "video", None):
                            continue

                    size = msg.file.size if getattr(msg, "file", None) else 0

                    print(f"  ⭐ Candidato encontrado en {chat_label}!")
                    print(f"     ID: {msg.id}")
                    print(f"     Archivo: {fname}")
                    print(f"     Tamaño: {format_size(size)}")
                    print(f"     Caption: {caption[:120]}")

                    candidates.append({
                        "chat_label": chat_label,
                        "chat_entity": target_entity,
                        "msg": msg,
                        "fname": fname,
                        "size": size,
                        "caption": caption
                    })
            except Exception as e:
                print(f"  Error en búsqueda '{q}' en {chat_label}: {e}")

    if not candidates:
        print("\n❌ No se encontraron versiones en MP4 o MKV de 'Esta casa es una ruina' en los grupos escaneados.")
        await bunker_client.disconnect()
        await prod_client.disconnect()
        return

    # 3. Seleccionar el mejor candidato (preferir mkv/mp4 en español / castellano / 1080p / mayor tamaño)
    print(f"\n--- 3. Analizando {len(candidates)} candidatos encontrados ---")
    
    # Ordenar por tamaño y calidad
    def score_candidate(cand):
        score = 0
        name = (cand["fname"] + " " + cand["caption"]).lower()
        if "1080" in name: score += 50
        elif "720" in name: score += 30
        if "castellano" in name or "spanish" in name or "esp" in name: score += 40
        if "dual" in name or "multi" in name: score += 30
        if cand["fname"].lower().endswith(".mkv"): score += 10
        elif cand["fname"].lower().endswith(".mp4"): score += 8
        score += min(cand["size"] / (1024 * 1024 * 100), 20) # Preferir hasta ~2GB de calidad
        return score

    candidates.sort(key=score_candidate, reverse=True)
    best = candidates[0]
    print(f"\n🏆 Mejor candidato seleccionado:")
    print(f"   Origen: {best['chat_label']} (Msg ID: {best['msg'].id})")
    print(f"   Archivo: {best['fname']}")
    print(f"   Tamaño: {format_size(best['size'])}")
    print(f"   Puntaje de calidad: {score_candidate(best)}")

    # Preparar pie / caption limpio
    send_caption = best["caption"].strip()
    if not send_caption or len(send_caption) < 5:
        send_caption = "Esta casa es una ruina (1986) [1080p Castellano Dual]"

    # 4. Mover / enviar a Bunker 80 y 90
    print("\n--- 4. Enviando al Búnker Cine de los 80 y 90 ---")
    bunker_chat = await bunker_client.get_entity(BUNKER_80_90)
    bunker_msg = None
    try:
        bunker_msg = await bunker_client.send_message(
            bunker_chat,
            message=send_caption,
            file=best["msg"].media
        )
        print(f"✅ Enviado con éxito al Búnker 80 y 90! Nuevo Msg ID: {bunker_msg.id}")
    except Exception as e:
        print(f"❌ Error enviando al Búnker: {e}")
        try:
            bunker_msg = await bunker_client.forward_messages(bunker_chat, best["msg"])
            print(f"✅ Reenviado al Búnker 80 y 90! ID: {bunker_msg.id}")
        except Exception as e2:
            print(f"❌ Falló reenvío al Búnker: {e2}")

    # 5. Mover / enviar a Producción 80 y 90
    print("\n--- 5. Enviando a Producción Cine de los 80 y 90 ---")
    prod_chat = await prod_client.get_entity(PROD_80_90)
    try:
        media_to_send = bunker_msg.media if bunker_msg else best["msg"].media
        prod_msg = await prod_client.send_message(
            prod_chat,
            message=send_caption,
            file=media_to_send
        )
        print(f"✅ Enviado con éxito a Producción 80 y 90! Nuevo Msg ID: {prod_msg.id}")
    except Exception as e:
        print(f"Aviso enviando con prod_client: {e}. Intentando forward...")
        try:
            prod_msg = await prod_client.forward_messages(prod_chat, bunker_msg or best["msg"])
            print(f"✅ Reenviado a Producción 80 y 90! ID: {prod_msg.id}")
        except Exception as e2:
            print(f"❌ Falló envío a Producción: {e2}")

    # 6. Limpieza opcional de la versión en inglés antigua
    if prod_existing:
        print("\n--- 6. Eliminando versión antigua en inglés de Producción ---")
        for old_msg in prod_existing:
            try:
                await prod_client.delete_messages(prod_chat, [old_msg.id])
                print(f"🗑️ Eliminado mensaje antiguo ID {old_msg.id} de Producción ({get_filename(old_msg)})")
            except Exception as e:
                print(f"No se pudo eliminar mensaje antiguo {old_msg.id}: {e}")

    print("\n🎉 Proceso completado exitosamente.")
    await bunker_client.disconnect()
    await prod_client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
