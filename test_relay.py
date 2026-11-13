import os
import sys
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ForwardMessagesRequest

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
    print(f"CB: {me_b.first_name} ({me_b.id}) | CP: {me_p.first_name} ({me_p.id})")

    await cb.get_dialogs(limit=None)
    await cp.get_dialogs(limit=None)

    # 1. Probar reenvio directo de cp en peliculas_infantiles (Msg 524, 525)
    b_inf = -1004383923903
    p_inf = -1004326583216
    try:
        eb = await cp.get_input_entity(b_inf)
        ep = await cp.get_input_entity(p_inf)
        res = await cp(ForwardMessagesRequest(
            from_peer=eb,
            to_peer=ep,
            id=[524, 525],
            random_id=[123456, 123457],
            drop_author=True
        ))
        print("✅ CP reenvío DIRECTO en Películas Infantiles (Policán): EXITOSO!")
    except Exception as e:
        print(f"❌ CP reenvío directo en Infantiles falló: {e}")

    await cb.disconnect()
    await cp.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
