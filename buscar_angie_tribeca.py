import asyncio
import os
import sys
import re
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")
TELEGRAM_STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION", "")

PROD_SERIES = -1004331019870
BUNKER_SERIES = -1002097175258
COMMUNITY_SERIES = -1002257262928
TOPIC_ANGIE = 3605

async def main():
    print("==================================================")
    print("1. INSPECCIÓN DETALLADA DEL TEMA 3605 EN PRODUCCIÓN")
    print("==================================================")
    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client_prod:
        prod_entity = await client_prod.get_entity(PROD_SERIES)
        
        # Listar todos los mensajes dentro del topic 3605
        topic_msgs = []
        async for m in client_prod.iter_messages(prod_entity, reply_to=TOPIC_ANGIE):
            if m.id == TOPIC_ANGIE:
                continue
            topic_msgs.append(m)

        print(f"Total mensajes actuales en topic {TOPIC_ANGIE}: {len(topic_msgs)}")
        avi_count = 0
        mkv_count = 0
        mp4_count = 0
        text_count = 0
        for m in topic_msgs:
            if m.file:
                fn = (getattr(m.file, 'name', '') or '').lower()
                if fn.endswith('.avi'):
                    avi_count += 1
                elif fn.endswith('.mkv'):
                    mkv_count += 1
                elif fn.endswith('.mp4'):
                    mp4_count += 1
            elif m.text:
                text_count += 1

        print(f"  • Mensajes de texto/sinopsis: {text_count}")
        print(f"  • Archivos .avi: {avi_count}")
        print(f"  • Archivos .mkv: {mkv_count}")
        print(f"  • Archivos .mp4: {mp4_count}")
        print(f"Rango de IDs de mensajes a borrar: {[m.id for m in topic_msgs[:5]]} ... {[m.id for m in topic_msgs[-5:]] if len(topic_msgs)>5 else ''}")

        # Comprobar en Búnker Series
        print("\n==================================================")
        print("2. BUSCANDO 'ANGIE TRIBECA' EN BÚNKER SERIES")
        print("==================================================")
        bunker_entity = await client_prod.get_entity(BUNKER_SERIES)
        bunker_matches = []
        async for m in client_prod.iter_messages(bunker_entity, search="Angie Tribeca", limit=50):
            if m.file:
                fn = getattr(m.file, 'name', '') or ''
                bunker_matches.append((m.id, fn, m.reply_to_msg_id))
        print(f"Archivos encontrados en Búnker: {len(bunker_matches)}")
        for bid, bfn, btop in bunker_matches[:5]:
            print(f"  [Msg {bid} | Topic {btop}] {bfn}")

    # Buscar en Comunidad Castellana con TELEGRAM_STRING_SESSION
    if TELEGRAM_STRING_SESSION:
        print("\n==================================================")
        print("3. BUSCANDO 'ANGIE TRIBECA' EN COMUNIDAD CASTELLANA")
        print("==================================================")
        try:
            async with TelegramClient(StringSession(TELEGRAM_STRING_SESSION), API_ID, API_HASH) as client_comm:
                comm_entity = await client_comm.get_entity(COMMUNITY_SERIES)
                print(f"Conectado a '{comm_entity.title}' ({comm_entity.id})")
                
                # Buscar con search
                comm_results = []
                async for m in client_comm.iter_messages(comm_entity, search="Angie Tribeca", limit=100):
                    if m.file:
                        fn = (getattr(m.file, 'name', '') or '')
                        top = getattr(m.reply_to, 'reply_to_top_id', None) or getattr(m.reply_to, 'reply_to_msg_id', None)
                        comm_results.append((m.id, fn, top))
                    elif m.text and ("tribeca" in m.text.lower() or "angie" in m.text.lower()):
                        top = getattr(m.reply_to, 'reply_to_top_id', None) or getattr(m.reply_to, 'reply_to_msg_id', None)
                        comm_results.append((m.id, f"TXT: {m.text[:60]}", top))

                print(f"Total coincidencias en Comunidad Castellana: {len(comm_results)}")
                mkv_comm = [r for r in comm_results if r[1].lower().endswith('.mkv')]
                mp4_comm = [r for r in comm_results if r[1].lower().endswith('.mp4')]
                avi_comm = [r for r in comm_results if r[1].lower().endswith('.avi')]
                print(f"  • Encontrados MKV: {len(mkv_comm)}")
                print(f"  • Encontrados MP4: {len(mp4_comm)}")
                print(f"  • Encontrados AVI: {len(avi_comm)}")
                
                for mid, mfn, mtop in comm_results[:10]:
                    print(f"  [Msg {mid} | Topic {mtop}] {mfn}")

                # Búsqueda global con la cuenta secundaria
                print("\nBúsqueda global en todos los chats accesibles de la cuenta:")
                async for m in client_comm.iter_messages(None, search="Angie Tribeca", limit=30):
                    if m.file:
                        fn = getattr(m.file, 'name', '') or ''
                        ctitle = getattr(m.chat, 'title', str(m.chat_id))
                        print(f"  -> En '{ctitle}': {fn}")
        except Exception as e:
            print(f"Error explorando Comunidad Castellana: {e}")

if __name__ == "__main__":
    asyncio.run(main())
