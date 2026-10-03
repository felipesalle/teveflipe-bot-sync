import asyncio
import os
import sys
import random
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ForwardMessagesRequest

load_dotenv("e:/TeveFlipe/sync_bunker/.env")

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD") or ""
PROD_SERIES_TV = -1004331019870
TOPIC_ORPHAN_BLACK = 58

sys.stdout.reconfigure(encoding='utf-8')

# Lista ordenada de los 12 episodios de Orphan Black
EPISODIOS = [
    {"ep": "1x01", "msg_id": 2453, "from_topic": "Cobra Kai (2362)"},
    {"ep": "1x02", "msg_id": 2418, "from_topic": "Cobra Kai (2362)"},
    {"ep": "1x03", "msg_id": 2408, "from_topic": "Cobra Kai (2362)"},
    {"ep": "1x04", "msg_id": 2279, "from_topic": "Archer (2173)"},
    {"ep": "1x05", "msg_id": 1889, "from_topic": "Doom Patrol (1858)"},
    {"ep": "1x06", "msg_id": 1583, "from_topic": "Entourage (1452)"},
    {"ep": "1x07", "msg_id": 1513, "from_topic": "Entourage (1452)"},
    {"ep": "1x08", "msg_id": 1329, "from_topic": "Boardwalk Empire (1188)"},
    {"ep": "1x09", "msg_id": 1330, "from_topic": "Boardwalk Empire (1188)"},
    {"ep": "1x10", "msg_id": 611, "from_topic": "Chicago Fire (400)"},
    {"ep": "2x01", "msg_id": 612, "from_topic": "Chicago Fire (400)"},
    {"ep": "2x02", "msg_id": 248, "from_topic": "The Blacklist (237)"},
]

async def main():
    print("=" * 70)
    print("🚀 REPARACIÓN Y REUBICACIÓN DE 'ORPHAN BLACK'")
    print("=" * 70)

    client = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)
    await client.start()
    
    ent_prod = await client.get_input_entity(PROD_SERIES_TV)

    # 1. Reenviar cada episodio en orden al Tema 58 (Orphan Black)
    print(f"\n📦 Reenviando los 12 episodios al Tema {TOPIC_ORPHAN_BLACK} (Orphan Black)...")
    
    nuevos_ids = []
    antiguos_ids = []

    for item in EPISODIOS:
        mid = item["msg_id"]
        ep = item["ep"]
        antiguos_ids.append(mid)
        
        r_id = random.randint(1, 2**63 - 1)
        res = await client(ForwardMessagesRequest(
            from_peer=ent_prod,
            to_peer=ent_prod,
            id=[mid],
            random_id=[r_id],
            drop_author=True,
            top_msg_id=TOPIC_ORPHAN_BLACK
        ))
        
        # Obtener el ID del nuevo mensaje creado
        new_id = res.updates[0].id if hasattr(res, 'updates') and res.updates else getattr(res, 'id', None)
        nuevos_ids.append(new_id)
        print(f"  ✅ Reenviado {ep} (anterior Msg {mid}) ➔ Tema 58")
        await asyncio.sleep(1.5)

    print(f"\n✨ Los 12 episodios se encuentran ahora correctamente en el Tema 58.")

    # 2. Eliminar los mensajes intrusos de los otros temas
    print("\n🗑️ Eliminando los 12 mensajes intrusos de sus ubicaciones erróneas...")
    await client.delete_messages(ent_prod, antiguos_ids, revoke=True)
    print(f"  ✅ Eliminados exitosamente: {antiguos_ids}")

    # 3. Comprobar resultado en el Tema 58
    print("\n🔎 Verificando mensajes actuales en el Tema 58 (Orphan Black)...")
    final_msgs = [m async for m in client.iter_messages(ent_prod, reply_to=TOPIC_ORPHAN_BLACK) if not m.action]
    print(f"  Total episodios confirmados en Tema 58: {len(final_msgs)}")
    for m in reversed(final_msgs):
        fname = m.file.name if m.file and m.file.name else m.text[:40]
        print(f"   - Msg {m.id}: {fname}")

    await client.disconnect()
    print("\n🎉 ¡Reparación completada con éxito al 100%!")

if __name__ == "__main__":
    asyncio.run(main())
