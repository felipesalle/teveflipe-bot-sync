import os
import sys
import json
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import InviteToChannelRequest, EditAdminRequest
from telethon.tl.functions.messages import ToggleNoForwardsRequest
from telethon.tl.types import ChatAdminRights

API_ID = int(os.getenv('TELEGRAM_API_ID', '28045969'))
API_HASH = os.getenv('TELEGRAM_API_HASH', 'd8e515c5687943e5e0bf046f87c3d2cc')
SESSION_BUNKER = os.getenv('SESSION_BUNKER')
SESSION_PROD = os.getenv('SESSION_PROD')

async def main():
    cb = TelegramClient(StringSession(SESSION_BUNKER), API_ID, API_HASH)
    cp = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)
    await cb.start()
    await cp.start()

    me_b = await cb.get_me()
    me_p = await cp.get_me()
    print(f"Bunker user: {me_b.first_name} ({me_b.id})")
    print(f"Prod user: {me_p.first_name} ({me_p.id})")

    with open('canales_map.json', 'r', encoding='utf-8') as f:
        canales = json.load(f)

    # 1. Probar deshabilitar no_forwards en Peliculas Anime Bunker
    anime_bunker_id = -1004440781202
    try:
        ent_ab = await cb.get_entity(anime_bunker_id)
        await cb(ToggleNoForwardsRequest(peer=ent_ab, enabled=False))
        print("✅ No-forwards deshabilitado exitosamente en Peliculas Anime Bunker")
    except Exception as e:
        print(f"⚠️ Error al modificar no_forwards en Anime: {e}")

    # 2. Agregar a cb como admin en canales de produccion donde cp es admin
    rights = ChatAdminRights(
        post_messages=True,
        edit_messages=True,
        delete_messages=True,
        ban_users=True,
        invite_users=True,
        pin_messages=True,
        manage_topics=True
    )

    for cid in ['documentales', 'conciertos', 'series_turcas', 'peliculas_infantiles', 'peliculas_anime']:
        c = next(x for x in canales if x['id'] == cid)
        pid = c['produccion_id']
        try:
            ep = await cp.get_entity(pid)
            try:
                await cp(InviteToChannelRequest(channel=ep, users=[me_b]))
                print(f"✅ {cid}: me_b invitado a Producción")
            except Exception as ie:
                print(f"ℹ️ {cid}: invite check: {ie}")

            try:
                await cp(EditAdminRequest(channel=ep, user_id=me_b, admin_rights=rights, rank="Admin"))
                print(f"✅ {cid}: me_b promovido a Admin en Producción")
            except Exception as ae:
                print(f"ℹ️ {cid}: admin check: {ae}")
        except Exception as e:
            print(f"❌ {cid}: error en canal de producción: {e}")

    await cb.disconnect()
    await cp.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
