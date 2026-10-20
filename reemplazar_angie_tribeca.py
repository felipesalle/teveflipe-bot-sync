import asyncio
import os
import sys
import re
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
    # ej: 1x01 - Angie Tribeca.mkv o S01E01
    m = re.search(r'(?:(\d{1,2})x(\d{1,2})|[sS](\d{1,2})[eE](\d{1,2}))', filename)
    if m:
        season = int(m.group(1) or m.group(3))
        episode = int(m.group(2) or m.group(4))
        return (season, episode)
    return (99, 99)

async def main():
    print("🚀 INICIANDO SUSTITUCIÓN Y LIMPIEZA DE ANGIE TRIBECA")
    
    # 1. Conectar con TELEGRAM_STRING_SESSION para recuperar los 40 episodios oficiales en MKV
    print("\n📡 1. Recuperando los 40 episodios MKV desde Comunidad Castellana...")
    mkv_episodes = []
    
    async with TelegramClient(StringSession(TELEGRAM_STRING_SESSION), API_ID, API_HASH) as client_comm:
        comm_ent = await client_comm.get_entity(COMMUNITY_SERIES)
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

        # Ordenar cronológicamente T1E01 -> T4E10
        mkv_episodes.sort(key=lambda x: x["sort_key"])
        print(f"✅ Recuperados y ordenados {len(mkv_episodes)} capítulos en MKV:")
        for ep in mkv_episodes[:5]:
            print(f"   • T{ep['sort_key'][0]}E{ep['sort_key'][1]}: {ep['filename']} (ID: {ep['msg_id']})")
        print(f"   ... ({len(mkv_episodes)-10} episodios intermedios) ...")
        for ep in mkv_episodes[-5:]:
            print(f"   • T{ep['sort_key'][0]}E{ep['sort_key'][1]}: {ep['filename']} (ID: {ep['msg_id']})")

    if len(mkv_episodes) < 40:
        print(f"⚠️ Atención: Solo se encontraron {len(mkv_episodes)} episodios MKV en lugar de 40.")

    # 2. Conectar con SESSION_PROD para borrar los mensajes .avi antiguos en el tema 3605
    print("\n🗑️ 2. Borrando mensajes viejos .avi en el tema 3605 de Producción...")
    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client_prod:
        prod_ent = await client_prod.get_entity(PROD_SERIES)
        
        msgs_to_delete = []
        async for m in client_prod.iter_messages(prod_ent, reply_to=TOPIC_ANGIE):
            if m.id != TOPIC_ANGIE:
                msgs_to_delete.append(m.id)

        print(f"Total mensajes antiguos a eliminar en topic {TOPIC_ANGIE}: {len(msgs_to_delete)}")
        if msgs_to_delete:
            # Borrar en lotes de 50
            for i in range(0, len(msgs_to_delete), 50):
                chunk = msgs_to_delete[i:i+50]
                await client_prod.delete_messages(prod_ent, chunk)
                print(f"   ✓ Eliminados {len(chunk)} mensajes...")
                await asyncio.sleep(1)
        print("✅ Tema 3605 limpiado por completo.")

        # 3. Enviar sinopsis limpia primero
        sinopsis = (
            "**Angie Tribeca** (Serie de TV, 2016–2018)\n\n"
            "• **Temporadas:** 4 (Completa)\n"
            "• **Episodios:** 40\n"
            "• **Formato:** MKV 1080p / 720p Dual Castellano\n"
            "• **Género:** Comedia, Policíaco, Sátira\n\n"
            "**Sinopsis:** Parodia policiaca creada por Steve Carell y Nancy Walls Carell. "
            "Sigue a la veterana detective Angie Tribeca (Rashida Jones) y a un equipo de excéntricos "
            "investigadores del Departamento de Policía de Los Ángeles mientras resuelven los crímenes más disparatados."
        )
        await client_prod.send_message(prod_ent, sinopsis, reply_to=TOPIC_ANGIE)
        print("✅ Sinopsis publicada en el tema.")

    # 4. Reenviar los 40 episodios MKV ordenados desde Comunidad Castellana hacia Producción
    print("\n📦 3. Reenviando los 40 episodios MKV en orden cronológico...")
    async with TelegramClient(StringSession(TELEGRAM_STRING_SESSION), API_ID, API_HASH) as client_comm:
        comm_ent = await client_comm.get_entity(COMMUNITY_SERIES)
        prod_ent = await client_comm.get_entity(PROD_SERIES)
        
        source_msg_ids = [ep["msg_id"] for ep in mkv_episodes]
        
        # Reenviar en bloques de 5 para evitar bloqueos
        for i in range(0, len(source_msg_ids), 5):
            batch = source_msg_ids[i:i+5]
            await client_comm(ForwardMessagesRequest(
                from_peer=comm_ent,
                to_peer=prod_ent,
                id=batch,
                top_msg_id=TOPIC_ANGIE,
                drop_author=True
            ))
            print(f"   ✓ Reenviados episodios {i+1} a {min(i+5, len(source_msg_ids))} de {len(source_msg_ids)}...")
            await asyncio.sleep(2)

    print("\n🎉 ¡PROCESO COMPLETADO CON ÉXITO! Angie Tribeca está limpia y en calidad MKV en Producción.")

if __name__ == "__main__":
    asyncio.run(main())
