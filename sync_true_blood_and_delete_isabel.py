import asyncio
import os
import random
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import (
    ForwardMessagesRequest,
    DeleteTopicHistoryRequest,
    ToggleNoForwardsRequest
)

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_BUNKER = os.getenv("SESSION_BUNKER", "")
SESSION_PROD = os.getenv("SESSION_PROD", "")

BUNKER_SERIES = -1002097175258
PROD_SERIES = -1004331019870
BUNKER_TOPIC_TRUE_BLOOD = 26137
PROD_TOPIC_TRUE_BLOOD = 9464

async def safe_sleep(secs: float):
    await asyncio.sleep(secs)

async def main():
    if not SESSION_BUNKER or not SESSION_PROD:
        print("❌ ERROR: Faltan credenciales SESSION_BUNKER o SESSION_PROD.")
        return

    cb = TelegramClient(StringSession(SESSION_BUNKER), API_ID, API_HASH)
    cp = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)

    await cb.start()
    await cp.start()

    me_p = await cp.get_me()
    me_b = await cb.get_me()
    print(f"Bunker User: {me_b.first_name} (ID: {me_b.id})")
    print(f"Prod User: {me_p.first_name} (ID: {me_p.id})")

    prod_user = await cb.get_input_entity(me_p.id)
    bunker_user = await cp.get_input_entity(me_b.id)

    ent_bunker = await cb.get_input_entity(BUNKER_SERIES)
    ent_prod = await cp.get_input_entity(PROD_SERIES)

    # 1. Desactivar temporalmente noforwards en Búnker usando la cuenta de Búnker (admin)
    was_protected = False
    try:
        full_bunker = await cb.get_entity(ent_bunker)
        if getattr(full_bunker, 'noforwards', False):
            print("🔓 Desactivando temporalmente restricción 'noforwards' en Búnker...")
            await cb(ToggleNoForwardsRequest(peer=ent_bunker, enabled=False))
            was_protected = True
            print("✅ noforwards deshabilitado.")
    except Exception as e:
        print(f"⚠️ Aviso al consultar/modificar noforwards: {e}")

    try:
        # 2. Recopilar capítulos de True Blood desde el Búnker
        print(f"\n📥 Leyendo capítulos de 'True Blood' desde Búnker (Topic {BUNKER_TOPIC_TRUE_BLOOD})...")
        bunker_msg_ids = []
        async for m in cb.iter_messages(ent_bunker, reply_to=BUNKER_TOPIC_TRUE_BLOOD, reverse=True):
            if m.id == BUNKER_TOPIC_TRUE_BLOOD:
                continue
            if m.file:
                bunker_msg_ids.append(m.id)

        print(f"Total capítulos encontrados en Búnker: {len(bunker_msg_ids)}")

        if not bunker_msg_ids:
            print("❌ No se encontraron mensajes con archivos en el tema de Búnker.")
            return

        # 3. Reenviar a Producción Topic 9464
        print(f"\n🚀 Sincronizando {len(bunker_msg_ids)} capítulos a Producción (Topic {PROD_TOPIC_TRUE_BLOOD})...")
        chunk_size = 5
        total = len(bunker_msg_ids)

        for i in range(0, total, chunk_size):
            chunk = bunker_msg_ids[i:i + chunk_size]
            for attempt in range(1, 4):
                try:
                    # Método DM puente: cb -> cp -> Prod
                    fwd_res = await cb.forward_messages(
                        entity=prod_user,
                        messages=chunk,
                        from_peer=ent_bunker,
                        drop_author=True
                    )
                    b_fwd = [m.id for m in fwd_res] if isinstance(fwd_res, list) else [fwd_res.id]

                    recv = await cp.get_messages(bunker_user, limit=len(b_fwd))
                    if not isinstance(recv, list):
                        recv = [recv]
                    p_recv = [m.id for m in reversed(recv) if not m.action]

                    if p_recv:
                        r_ids = [random.randint(1, 2**63 - 1) for _ in p_recv]
                        await cp(ForwardMessagesRequest(
                            from_peer=await cp.get_input_entity(bunker_user),
                            to_peer=ent_prod,
                            id=p_recv,
                            random_id=r_ids,
                            drop_author=True,
                            top_msg_id=PROD_TOPIC_TRUE_BLOOD
                        ))

                    # Limpieza en DM
                    try:
                        await cb.delete_messages(prod_user, b_fwd, revoke=True)
                        await cp.delete_messages(bunker_user, p_recv, revoke=True)
                    except Exception:
                        pass

                    print(f"   [{min(i + chunk_size, total)}/{total}] Reenviados {len(chunk)} capítulos.", flush=True)
                    await safe_sleep(1.5)
                    break
                except errors.FloodWaitError as fe:
                    print(f"   ⏳ FloodWait: esperando {fe.seconds}s...", flush=True)
                    await safe_sleep(fe.seconds + 2)
                except Exception as e:
                    print(f"   ⚠️ Error en lote {chunk} (intento {attempt}): {e}", flush=True)
                    await safe_sleep(3.0)

    finally:
        if was_protected:
            try:
                print("🔒 Restaurando restricción 'noforwards' en Búnker...")
                await cb(ToggleNoForwardsRequest(peer=ent_bunker, enabled=True))
                print("✅ noforwards restaurado.")
            except Exception as e:
                print(f"⚠️ Error restaurando noforwards: {e}")

        await cb.disconnect()
        await cp.disconnect()

    print("\n🔍 Verificación completa de sincronización.")

if __name__ == "__main__":
    asyncio.run(main())
