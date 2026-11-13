
import os, sys, json, asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

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
    print(f'Bunker user: {me_b.first_name} ({me_b.id})')
    print(f'Prod user: {me_p.first_name} ({me_p.id})')
    
    with open('canales_map.json', 'r', encoding='utf-8') as f:
        canales = json.load(f)
        
    for c in canales:
        cid = c['id']
        bid = c.get('bunker_id')
        pid = c.get('produccion_id')
        
        # Check bunker access
        b_acc = 'None'
        try:
            eb = await cb.get_entity(bid)
            b_acc = f'OK ({eb.title})'
        except Exception as e:
            b_acc = f'ERR ({e})'
            
        # Check prod access by Bunker user
        p_acc_b = 'None'
        try:
            ep = await cb.get_entity(pid)
            perm = await cb.get_permissions(ep)
            p_acc_b = 'OK (Canal/Admin)' if perm is None or perm.send_messages else 'Read-Only'
        except Exception as e:
            p_acc_b = f'ERR ({e})'
            
        print(f'{cid}: Bunker={b_acc} | Prod(cb)={p_acc_b}')
        
    await cb.disconnect()
    await cp.disconnect()

asyncio.run(main())
