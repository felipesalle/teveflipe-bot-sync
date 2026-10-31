import os
import sys
import asyncio
import json
import time
from telethon import TelegramClient, errors
from telethon.sessions import StringSession

sys.stdout.reconfigure(encoding='utf-8')

API_ID = int(os.environ['TELEGRAM_API_ID'])
API_HASH = os.environ['TELEGRAM_API_HASH']
SESSION_BUNKER = os.environ.get('SESSION_BUNKER') or os.environ.get('TELEGRAM_STRING_SESSION')

ORIGIN_ID = -1001905652210
TARGET_ID = -5498750167

QUEUE_FILE = "movies_copy_queue.json"
STATE_FILE = "copia_todas_peliculas_state.json"

MAX_RUN_SECONDS = int(os.environ.get('MAX_RUN_SECONDS', 18000))  # 5 horas por defecto

async def main():
    if not os.path.exists(QUEUE_FILE):
        print(f"Error: {QUEUE_FILE} no existe.", flush=True)
        return

    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
        queue = json.load(f)

    state = {"copied_keys": []}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            state = {"copied_keys": []}

    copied_set = set(state.get("copied_keys", []))

    client = TelegramClient(StringSession(SESSION_BUNKER), API_ID, API_HASH)
    await client.start()

    origin_ent = await client.get_input_entity(ORIGIN_ID)
    target_ent = await client.get_input_entity(TARGET_ID)

    total_movies = len(queue)
    already_copied = len(copied_set)

    print("=" * 70, flush=True)
    print("INICIANDO REPLICACIÓN EN GITHUB ACTIONS AL BÚNKER (-5498750167)", flush=True)
    print(f"Total películas en cola: {total_movies}", flush=True)
    print(f"Ya copiadas previamente: {already_copied}", flush=True)
    print(f"Tiempo máximo de ejecución: {MAX_RUN_SECONDS/3600:.1f} horas", flush=True)
    print("=" * 70, flush=True)

    t_start = time.time()

    for idx, m in enumerate(queue, 1):
        # Verificar si nos acercamos al límite de tiempo para guardar y salir limpiamente
        if time.time() - t_start > MAX_RUN_SECONDS:
            print("⏳ Tiempo límite del job alcanzado. Guardando estado y finalizando...", flush=True)
            break

        m_key = m["base_prefix"].lower()
        if m_key in copied_set:
            continue

        title = m["title"]
        year_str = f" ({m['year']})" if m.get("year") else ""
        part_count = m["part_count"]
        size_str = m["total_size_formatted"]
        quality = m["quality"]

        print(f"[{idx}/{total_movies}] Copiando 🎬 {title}{year_str} | {part_count} partes | {size_str}...", flush=True)

        # 1. Enviar tarjeta identificadora
        card_text = (
            f"🎬 **{title}**{year_str}\n"
            f"📺 **Calidad:** `{quality}`\n"
            f"📦 **Partes:** {part_count} archivos\n"
            f"💾 **Tamaño Total:** {size_str}"
        )

        while True:
            try:
                await client.send_message(target_ent, card_text)
                await asyncio.sleep(1.8)
                break
            except errors.FloodWaitError as fe:
                print(f"   ⚠️ FloodWait al enviar tarjeta: esperando {fe.seconds}s...", flush=True)
                await asyncio.sleep(fe.seconds + 2)
            except Exception as e:
                print(f"   ❌ Error enviando tarjeta de {title}: {e}", flush=True)
                await asyncio.sleep(3)
                break

        # 2. Reenviar partes
        files_sorted = sorted(m["files"], key=lambda x: x["filename"].lower())
        msg_ids = [f["msg_id"] for f in files_sorted]
        batch_size = 10
        success = True

        for b_start in range(0, len(msg_ids), batch_size):
            chunk = msg_ids[b_start:b_start + batch_size]
            while True:
                try:
                    await client.forward_messages(
                        entity=target_ent,
                        messages=chunk,
                        from_peer=origin_ent,
                        drop_author=True
                    )
                    await asyncio.sleep(2.0)
                    break
                except errors.FloodWaitError as fe:
                    print(f"   ⚠️ FloodWait reenviando partes: esperando {fe.seconds}s...", flush=True)
                    await asyncio.sleep(fe.seconds + 2)
                except Exception as e:
                    print(f"   ❌ Error reenviando lote de {title}: {e}", flush=True)
                    success = False
                    await asyncio.sleep(3)
                    break

        if success:
            state["copied_keys"].append(m_key)
            with open(STATE_FILE, "w", encoding="utf-8") as sf:
                json.dump(state, sf, ensure_ascii=False, indent=2)
            print(f"   ✅ ¡{title} copiada con éxito! ({len(state['copied_keys'])}/{total_movies})", flush=True)

        await asyncio.sleep(2.0)

    await client.disconnect()
    print("=" * 70, flush=True)
    print(f"Progreso actual: {len(state['copied_keys'])}/{total_movies} películas copiadas.", flush=True)
    print("=" * 70, flush=True)

if __name__ == '__main__':
    asyncio.run(main())
