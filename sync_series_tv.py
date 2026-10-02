import asyncio
import json
import logging
import os
import random
import sys
from telethon import TelegramClient, utils, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import (
    ForwardMessagesRequest,
    CreateForumTopicRequest,
    GetForumTopicsRequest
)

# Configurar logging con salida inmediata en stdout
sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("SyncSeriesTV")

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_BUNKER = os.getenv("SESSION_BUNKER") or ""
SESSION_PROD = os.getenv("SESSION_PROD") or ""

BUNKER_SERIES_TV = int(os.getenv("BUNKER_SERIES_TV", "-1002097175258"))
PROD_SERIES_TV = int(os.getenv("PROD_SERIES_TV", "-1004331019870"))

STATE_FILE = "sync_state_series_tv.json"
SERIES_BATCH_LIMIT = int(os.getenv("SERIES_BATCH_LIMIT", "12"))  # Series a procesar por ejecución
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "5"))                  # Mensajes por lote de reenvío (5 seguro contra desconexiones MTProto)

def load_json(filepath: str, default=None):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Error leyendo {filepath}: {e}")
    return default() if callable(default) else (default or {})

def save_json(filepath: str, data: dict):
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error guardando {filepath}: {e}")

async def ensure_connected(client: TelegramClient, name: str = "Client"):
    if not client.is_connected():
        logger.info(f"🔄 Cliente {name} desconectado. Reconectando...")
        try:
            await client.connect()
            logger.info(f"✅ Cliente {name} conectado exitosamente.")
        except Exception as e:
            logger.warning(f"⚠️ Error conectando {name}: {e}. Reintentando en 3s...")
            await asyncio.sleep(3)
            await client.connect()

async def ensure_clients(cb: TelegramClient, cp: TelegramClient):
    await ensure_connected(cb, "Búnker")
    await ensure_connected(cp, "Producción")

async def get_all_bunker_topics(client, entity):
    topics = []
    offset_date = 0
    offset_id = 0
    offset_topic = 0
    while True:
        await ensure_connected(client, "Búnker")
        res = await client(GetForumTopicsRequest(
            peer=entity,
            offset_date=offset_date,
            offset_id=offset_id,
            offset_topic=offset_topic,
            limit=100
        ))
        if not res.topics:
            break
        for t in res.topics:
            if t.id != 1:  # Excluir tema General
                topics.append(t)
        if len(res.topics) < 100:
            break
        last = res.topics[-1]
        offset_date = last.date
        offset_id = last.top_message
        offset_topic = last.id
    return topics

async def get_or_create_prod_topic(cp: TelegramClient, prod_entity, title: str, state: dict) -> int:
    topics_map = state.setdefault("prod_topics_map", {})
    norm_key = title.strip().lower()

    if norm_key in topics_map:
        return topics_map[norm_key]

    clean_name = title.strip()[:120]
    for attempt in range(1, 5):
        try:
            await ensure_connected(cp, "Producción")
            logger.info(f"Creando nuevo tema en Producción: '{clean_name}' (Intento {attempt})...")
            created = await cp(CreateForumTopicRequest(
                peer=prod_entity,
                title=clean_name,
                random_id=random.randint(1, 2**63 - 1)
            ))
            new_tid = None
            for u in created.updates:
                if hasattr(u, 'id'):
                    new_tid = u.id
                    break
                if hasattr(u, 'message') and hasattr(u.message, 'action') and hasattr(u.message.action, 'title'):
                    new_tid = u.message.id
                    break

            if new_tid:
                logger.info(f"✨ Tema creado en Producción con ID: {new_tid}")
                topics_map[norm_key] = new_tid
                save_json(STATE_FILE, state)
                await asyncio.sleep(1.0)
                return new_tid
        except errors.FloodWaitError as fe:
            logger.warning(f"FloodWait de {fe.seconds}s creando tema '{clean_name}'. Esperando...")
            await asyncio.sleep(fe.seconds + 2)
        except Exception as e:
            logger.error(f"Error creando tema '{clean_name}': {e}")
            await asyncio.sleep(3.0)

    return 0

async def main():
    logger.info("=" * 80)
    logger.info("🚀 SINCRONIZACIÓN BÚNKER ➔ PRODUCCIÓN: '📺 SERIES TV'")
    logger.info("=" * 80)

    if not SESSION_BUNKER or not SESSION_PROD:
        logger.error("❌ ERROR: SESSION_BUNKER o SESSION_PROD no configuradas.")
        sys.exit(1)

    cb = TelegramClient(StringSession(SESSION_BUNKER), API_ID, API_HASH)
    cp = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)

    await cb.start()
    await cp.start()

    ent_bunker = await cb.get_input_entity(BUNKER_SERIES_TV)
    ent_prod = await cp.get_input_entity(PROD_SERIES_TV)

    me_p = await cp.get_me()
    me_b = await cb.get_me()
    prod_user = await cb.get_input_entity(me_p.id)
    bunker_user = await cp.get_input_entity(me_b.id)

    # Cargar estado
    state = load_json(STATE_FILE, default=lambda: {
        "completed_bunker_topics": [],
        "prod_topics_map": {},
        "total_messages_synced": 0
    })
    completed_set = set(state.get("completed_bunker_topics", []))

    # Obtener temas de búnker
    logger.info("📡 Obteniendo catálogo de temas de Búnker Series TV...")
    all_topics = await get_all_bunker_topics(cb, ent_bunker)
    logger.info(f"Total de temas encontrados en Búnker: {len(all_topics)}")

    pending_topics = [t for t in all_topics if t.id not in completed_set]
    logger.info(f"Temas ya sincronizados previamente: {len(completed_set)}")
    logger.info(f"Temas pendientes por sincronizar: {len(pending_topics)}")

    if not pending_topics:
        logger.info("🎉 ¡Todas las series de TV están completamente sincronizadas en Producción!")
        if os.path.exists(".more_series"):
            try:
                os.remove(".more_series")
            except Exception:
                pass
        await cb.disconnect()
        await cp.disconnect()
        return

    # Lote a procesar en esta ejecución
    current_batch = pending_topics[:SERIES_BATCH_LIMIT]
    logger.info(f"🎯 Procesando lote de {len(current_batch)} series en esta ejecución...")

    processed_count = 0
    for idx, t in enumerate(current_batch, 1):
        stitle = t.title.strip()
        logger.info(f"\n[{idx}/{len(current_batch)}] 📺 Sincronizando serie: '{stitle}' (Tema Búnker {t.id})...")

        try:
            await ensure_clients(cb, cp)

            # 1. Obtener mensajes del tema en Búnker
            b_msgs = [m async for m in cb.iter_messages(ent_bunker, reply_to=t.id, reverse=True) if not m.action and (m.media or m.text)]
            msg_ids = [m.id for m in b_msgs]
            logger.info(f"   Episodios / archivos encontrados en Búnker: {len(msg_ids)}")

            if not msg_ids:
                logger.info("   Tema vacío en Búnker, marcando como completado.")
                state["completed_bunker_topics"].append(t.id)
                save_json(STATE_FILE, state)
                continue

            # 2. Crear u obtener tema en Producción
            p_tid = await get_or_create_prod_topic(cp, ent_prod, stitle, state)
            if not p_tid:
                logger.error(f"   ❌ No se pudo crear/obtener tema en Producción para '{stitle}'. Saltando...")
                continue

            # 3. Comprobar si ya existen mensajes en Producción (reanudación inteligente)
            p_msgs = [m async for m in cp.iter_messages(ent_prod, reply_to=p_tid) if not m.action and (m.media or m.text)]
            p_count = len(p_msgs)
            if p_count >= len(msg_ids):
                logger.info(f"   ℹ️ El tema en Producción ya contiene todos los episodios ({p_count}/{len(msg_ids)}). Marcando como completado.")
                if t.id not in state["completed_bunker_topics"]:
                    state["completed_bunker_topics"].append(t.id)
                save_json(STATE_FILE, state)
                continue
            elif p_count > 0:
                logger.info(f"   ℹ️ El tema en Producción ya tiene {p_count}/{len(msg_ids)} episodios. Reanudando desde episodio {p_count + 1}...")
                remaining_msg_ids = msg_ids[p_count:]
            else:
                remaining_msg_ids = msg_ids

            # 4. Replicar mensajes vía Relay seguro
            all_ok = True
            for i in range(0, len(remaining_msg_ids), CHUNK_SIZE):
                chunk = remaining_msg_ids[i:i + CHUNK_SIZE]
                exito_chunk = False
                for attempt in range(1, 4):
                    try:
                        await ensure_clients(cb, cp)

                        # A. Bunker -> DM Prod
                        fwd_res = await cb.forward_messages(
                            entity=prod_user,
                            messages=chunk,
                            from_peer=ent_bunker,
                            drop_author=True
                        )
                        b_fwd = [m.id for m in fwd_res] if isinstance(fwd_res, list) else [fwd_res.id]

                        # B. Prod recibe de DM
                        recv = await cp.get_messages(bunker_user, limit=len(b_fwd))
                        if not isinstance(recv, list):
                            recv = [recv]
                        p_recv = [m.id for m in reversed(recv) if not m.action]

                        # C. Prod reenvía al canal oficial
                        if p_recv:
                            r_ids = [random.randint(1, 2**63 - 1) for _ in p_recv]
                            await cp(ForwardMessagesRequest(
                                from_peer=await cp.get_input_entity(bunker_user),
                                to_peer=ent_prod,
                                id=p_recv,
                                random_id=r_ids,
                                drop_author=True,
                                top_msg_id=p_tid
                            ))

                        # D. Limpieza inmediata de DMs
                        try:
                            await cb.delete_messages(prod_user, b_fwd, revoke=True)
                            await cp.delete_messages(bunker_user, p_recv, revoke=True)
                        except Exception:
                            pass

                        exito_chunk = True
                        state["total_messages_synced"] = state.get("total_messages_synced", 0) + len(chunk)
                        curr_synced = p_count + i + len(chunk)
                        logger.info(f"   Replicados {curr_synced}/{len(msg_ids)} episodios en '{stitle}'...")
                        break
                    except errors.FloodWaitError as fe:
                        logger.warning(f"FloodWait de {fe.seconds}s. Esperando...")
                        await asyncio.sleep(fe.seconds + 2)
                    except Exception as ce:
                        logger.warning(f"Aviso en lote ({attempt}/3) para '{stitle}': {ce}")
                        await asyncio.sleep(4.0)
                        await ensure_clients(cb, cp)

                if not exito_chunk:
                    all_ok = False
                    logger.error(f"❌ Falló réplica de lote en '{stitle}'. Se continuará en siguiente tanda.")
                    break

                await asyncio.sleep(2.5)

            if all_ok:
                logger.info(f"✅ ¡Serie '{stitle}' sincronizada al 100% en Producción!")
                if t.id not in state["completed_bunker_topics"]:
                    state["completed_bunker_topics"].append(t.id)
                save_json(STATE_FILE, state)

            processed_count += 1
            await asyncio.sleep(2.0)

        except Exception as se:
            logger.error(f"❌ Error inesperado procesando serie '{stitle}' (Tema {t.id}): {se}")
            await asyncio.sleep(5.0)
            await ensure_clients(cb, cp)

    # Guardar estado final
    save_json(STATE_FILE, state)

    completed_set = set(state.get("completed_bunker_topics", []))
    remaining_after = [t for t in all_topics if t.id not in completed_set]
    logger.info("\n" + "=" * 80)
    logger.info(f"🎉 Tanda finalizada. Series procesadas en esta ejecución: {processed_count}")
    logger.info(f"Total acumulado: {len(completed_set)} / {len(all_topics)} series completadas.")
    logger.info(f"Total episodios sincronizados: {state.get('total_messages_synced', 0)}")
    logger.info(f"Series pendientes restantes: {len(remaining_after)}")

    if remaining_after:
        with open(".more_series", "w", encoding="utf-8") as f:
            f.write(str(len(remaining_after)))
        logger.info(f"Creado archivo .more_series ({len(remaining_after)} restantes) para auto-disparar siguiente lote.")
    else:
        logger.info("🎉 ¡TODO EL CATÁLOGO DE SERIES TV HA SIDO SINCRONIZADO AL 100%!")
        if os.path.exists(".more_series"):
            try:
                os.remove(".more_series")
            except Exception:
                pass

    try:
        await cb.disconnect()
        await cp.disconnect()
    except Exception:
        pass

if __name__ == '__main__':
    asyncio.run(main())
