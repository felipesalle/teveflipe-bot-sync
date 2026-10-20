import asyncio
import os
import sys
import re
import random
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ForwardMessagesRequest

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")
TELEGRAM_STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION", "")

PROD_SERIES = -1004331019870
COMMUNITY_SERIES = -1002257262928
TOPIC_ANGIE = 3605

def parse_episode_sort_key(filename: str):
    m = re.search(r'(?:(\d{1,2})x(\d{1,2})|[sS](\d{1,2})[eE](\d{1,2}))', filename)
    if m:
        season = int(m.group(1) or m.group(3))
        episode = int(m.group(2) or m.group(4))
        return (season, episode)
    return (99, 99)

async def main():
    print("🚀 INICIANDO SINCRONIZACIÓN Y LIMPIEZA DE ANGIE TRIBECA VÍA RELAY SEGURO")
    
    client_comm = TelegramClient(StringSession(TELEGRAM_STRING_SESSION), API_ID, API_HASH)
    client_prod = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)

    await client_comm.connect()
    await client_prod.connect()

    me_comm = await client_comm.get_me()
    me_prod = await client_prod.get_me()
    print(f"✅ Conectado Comm: {me_comm.first_name} (ID: {me_comm.id})")
    print(f"✅ Conectado Prod: {me_prod.first_name} (ID: {me_prod.id})")

    # 1. Recuperar los 40 episodios en MKV de Comunidad Castellana
    comm_ent = await client_comm.get_entity(COMMUNITY_SERIES)
    prod_ent = await client_prod.get_entity(PROD_SERIES)

    print("\n📡 1. Buscando los 40 episodios MKV oficiales...")
    mkv_episodes = []
    async for m in client_comm.iter_messages(comm_ent, search="Angie Tribeca", limit=100):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if fn.lower().endswith('.mkv') and 'angie tribeca' in fn.lower():
                s_key = parse_episode_sort_key(fn)
                mkv_episodes.append({
                    "msg_id": m.id,
                    "filename": fn,
                    "sort_key": s_key
                })

    mkv_episodes.sort(key=lambda x: x["sort_key"])
    print(f"✅ Total episodios encontrados y ordenados: {len(mkv_episodes)}")
    for ep in mkv_episodes[:3]:
        print(f"   • T{ep['sort_key'][0]}E{ep['sort_key'][1]}: {ep['filename']}")
    print("   ...")
    for ep in mkv_episodes[-3:]:
        print(f"   • T{ep['sort_key'][0]}E{ep['sort_key'][1]}: {ep['filename']}")

    # 2. Verificar estado actual del tema 3605 en Producción
    print(f"\n📡 2. Verificando tema {TOPIC_ANGIE} en Producción...")
    current_prod_msgs = []
    async for m in client_prod.iter_messages(prod_ent, reply_to=TOPIC_ANGIE):
        if m.id != TOPIC_ANGIE and not m.action:
            current_prod_msgs.append(m)

    # Si quedase algún .avi residual, borrarlo
    residual_avi = [m.id for m in current_prod_msgs if m.file and (getattr(m.file, 'name', '') or '').lower().endswith('.avi')]
    if residual_avi:
        print(f"Borrando {len(residual_avi)} archivos .avi residuales...")
        await client_prod.delete_messages(prod_ent, residual_avi)
        print("✓ Archivos residuales borrados.")

    # 3. Comprobar cuántos MKV ya están en Producción (reanudación inteligente)
    already_in_prod = [m for m in current_prod_msgs if m.file and (getattr(m.file, 'name', '') or '').lower().endswith('.mkv')]
    print(f"Episodios MKV ya presentes en Producción: {len(already_in_prod)} / {len(mkv_episodes)}")

    if len(already_in_prod) >= len(mkv_episodes):
        print("🎉 ¡Todos los episodios ya están sincronizados en Producción!")
        await client_comm.disconnect()
        await client_prod.disconnect()
        return

    remaining_episodes = mkv_episodes[len(already_in_prod):]
    print(f"Episodios pendientes de transferir: {len(remaining_episodes)}")

    # 4. Transferencia por Relay Seguro (Comm -> DM Prod -> Tema 3605 en Producción)
    CHUNK_SIZE = 5
    for i in range(0, len(remaining_episodes), CHUNK_SIZE):
        batch = remaining_episodes[i:i + CHUNK_SIZE]
        batch_ids = [b["msg_id"] for b in batch]
        
        print(f"\n🔄 Procesando lote {i // CHUNK_SIZE + 1} ({len(batch)} episodios): {[b['filename'] for b in batch]}...")

        # A. Comm -> DM Prod
        fwd_res = await client_comm.forward_messages(
            entity=me_prod,
            messages=batch_ids,
            from_peer=comm_ent,
            drop_author=True
        )
        fwd_dm_ids = [m.id for m in fwd_res] if isinstance(fwd_res, list) else [fwd_res.id]
        await asyncio.sleep(2)

        # B. Prod recupera desde DM con Comm
        recv = await client_prod.get_messages(me_comm, limit=len(fwd_dm_ids))
        if not isinstance(recv, list):
            recv = [recv]
        p_recv = [m.id for m in reversed(recv) if not m.action and m.file]

        # C. Prod reenvía al tema 3605 en Producción
        if p_recv:
            await client_prod(ForwardMessagesRequest(
                from_peer=await client_prod.get_input_entity(me_comm),
                to_peer=prod_ent,
                id=p_recv,
                top_msg_id=TOPIC_ANGIE,
                drop_author=True
            ))
            print(f"   ✓ Lote {i // CHUNK_SIZE + 1} publicado exitosamente en tema {TOPIC_ANGIE}.")

            # D. Limpieza del DM privado
            await client_prod.delete_messages(me_comm, p_recv)
            await client_comm.delete_messages(me_prod, fwd_dm_ids)

        await asyncio.sleep(2.5)

    print("\n🎉 ¡PROCESO DE REEMPLAZO COMPLETADO! Todos los episodios están en MKV y ordenados cronológicamente.")
    await client_comm.disconnect()
    await client_prod.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
