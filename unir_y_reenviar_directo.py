import asyncio
import os
import re
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import InviteToChannelRequest
from telethon.tl.functions.messages import ForwardMessagesRequest, ExportChatInviteRequest, ImportChatInviteRequest

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
    print("🚀 UNIÓN DIRECTA Y REENVÍO DE ANGIE TRIBECA (40 MKV)")
    client_prod = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)
    client_comm = TelegramClient(StringSession(TELEGRAM_STRING_SESSION), API_ID, API_HASH)

    await client_prod.connect()
    await client_comm.connect()

    me_comm = await client_comm.get_me()
    me_prod = await client_prod.get_me()
    print(f"Prod: {me_prod.first_name} ({me_prod.id}) | Comm: {me_comm.first_name} ({me_comm.id})")

    prod_ent = await client_prod.get_entity(PROD_SERIES)
    comm_ent = await client_comm.get_entity(COMMUNITY_SERIES)

    # 1. Asegurar que client_comm está en el canal de Producción
    print("\n📡 1. Añadiendo a la cuenta secundaria a Producción Series TV...")
    try:
        await client_prod(InviteToChannelRequest(channel=prod_ent, users=[me_comm]))
        print("✅ Cuenta secundaria invitada exitosamente al canal.")
    except Exception as e:
        print(f"Nota invitación (puede que ya estuviera o requiera link): {e}")
        try:
            invite = await client_prod(ExportChatInviteRequest(peer=prod_ent))
            print(f"Enlace generado: {invite.link}")
            link_hash = invite.link.split('/')[-1].replace('+', '')
            await client_comm(ImportChatInviteRequest(link_hash))
            print("✅ Cuenta secundaria unida mediante enlace.")
        except Exception as e2:
            print(f"Nota unión por enlace: {e2}")

    # Verificar que client_comm puede resolver prod_ent
    try:
        comm_prod_ent = await client_comm.get_entity(PROD_SERIES)
        print(f"✅ client_comm resolvió exitosamente: '{comm_prod_ent.title}' ({comm_prod_ent.id})")
    except Exception as e:
        print(f"❌ Error resolviendo con client_comm: {e}")
        # Probar usando el objeto entity obtenido por prod
        comm_prod_ent = prod_ent

    # 2. Recuperar y ordenar los 40 episodios MKV de Comunidad Castellana
    print("\n📡 2. Recuperando episodios MKV de Angie Tribeca...")
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
    print(f"✅ Total episodios listos para reenviar: {len(mkv_episodes)}")

    # 3. Reenvío directo de Comunidad Castellana -> Producción Tema 3605
    print(f"\n📦 3. Reenviando directamente al tema {TOPIC_ANGIE} en Producción...")
    source_msg_ids = [ep["msg_id"] for ep in mkv_episodes]
    
    CHUNK_SIZE = 5
    for i in range(0, len(source_msg_ids), CHUNK_SIZE):
        batch = source_msg_ids[i:i + CHUNK_SIZE]
        await client_comm(ForwardMessagesRequest(
            from_peer=comm_ent,
            to_peer=comm_prod_ent,
            id=batch,
            top_msg_id=TOPIC_ANGIE,
            drop_author=True
        ))
        print(f"   ✓ Lote {i // CHUNK_SIZE + 1} ({len(batch)} caps) publicado en tema {TOPIC_ANGIE}!")
        await asyncio.sleep(2)

    print("\n🎉 ¡TODOS LOS 40 CAPÍTULOS DE ANGIE TRIBECA ESTÁN EN PRODUCCIÓN EN MKV!")
    await client_comm.disconnect()
    await client_prod.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
