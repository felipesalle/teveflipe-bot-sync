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
    print(f"CB: {me_b.first_name} | CP: {me_p.first_name}")

    await cb.get_dialogs(limit=None)
    await cp.get_dialogs(limit=None)

    # Canal conciertos: Bunker=-1003567099600, Prod=-1004296746003
    b_con = -1003567099600
    p_con = -1004296746003
    msg_ids = [326949, 326950] # Queen Live In Budapest

    try:
        eb = await cb.get_input_entity(b_con)
        ep = await cp.get_input_entity(p_con)
        
        # Paso 1: CB reenvia a CP en privado
        logger_step1 = await cb(ForwardMessagesRequest(
            from_peer=eb,
            to_peer=await cb.get_input_entity(me_p.id),
            id=msg_ids,
            random_id=[9991, 9992],
            drop_author=True
        ))
        print("✅ Paso 1 (CB -> CP en privado): EXITOSO!")

        # Obtener los IDs de los mensajes recién recibidos en CP
        received_msgs = [m.id async for m in cp.iter_messages(me_b.id, limit=len(msg_ids))]
        received_msgs.reverse()
        print(f"Mensajes recibidos en CP: {received_msgs}")

        # Paso 2: CP reenvia a Producción
        await cp(ForwardMessagesRequest(
            from_peer=await cp.get_input_entity(me_b.id),
            to_peer=ep,
            id=received_msgs,
            random_id=[8881, 8882],
            drop_author=True
        ))
        print("✅ Paso 2 (CP -> Producción): EXITOSO!")

        # Paso 3: Limpiar mensajes temporales en privado
        await cp.delete_messages(me_b.id, received_msgs)
        print("✅ Paso 3 (Limpieza de temporales): EXITOSO!")

    except Exception as e:
        print(f"❌ Error en relay: {e}")

    await cb.disconnect()
    await cp.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
