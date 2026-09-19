import os
import sys
import json
import asyncio
import logging
import random
from collections import defaultdict
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import (
    GetForumTopicsRequest,
    DeleteTopicHistoryRequest,
    EditForumTopicRequest,
    ForwardMessagesRequest,
    DeleteMessagesRequest,
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("RepararSeriesTV")

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION", "")
SERIES_DEST_CHAT = int(os.getenv("SERIES_DEST_CHAT", "-1002097175258"))
STATE_FILE = "sync_state.json"
DRY_RUN = os.getenv("DRY_RUN", "false").lower() in ("true", "1", "yes")


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    logger.info(f"💾 Estado actualizado en {STATE_FILE}")


def extract_text_or_filename(msg) -> str:
    parts = []
    if msg.text:
        parts.append(msg.text)
    if msg.file and getattr(msg.file, "name", None):
        parts.append(msg.file.name)
    return " | ".join(parts)


async def forward_or_copy_messages(client: TelegramClient, chat_peer, msgs: list, target_topic_id: int):
    """Mueve mensajes a un tema objetivo de forma segura."""
    if not msgs:
        return
    msg_ids = [m.id for m in msgs]
    rand_ids = [random.randint(1, 2**63 - 1) for _ in msg_ids]
    
    # Intentar ForwardMessagesRequest directo sin remitente
    try:
        await client(ForwardMessagesRequest(
            from_peer=chat_peer,
            to_peer=chat_peer,
            id=msg_ids,
            random_id=rand_ids,
            top_msg_id=target_topic_id,
            drop_author=True
        ))
        logger.info(f"   -> {len(msgs)} mensaje(s) reenviados al tema {target_topic_id}")
        await asyncio.sleep(2.0)
        return
    except Exception as e:
        logger.warning(f"   -> Falló reenvío por lote ({e}), copiando individualmente...")

    # Fallback individual
    for m in msgs:
        try:
            caption = m.text or (m.file.name if m.file else "Episodio")
            await client.send_message(
                chat_peer,
                message=caption,
                file=m.media,
                reply_to=target_topic_id
            )
            await asyncio.sleep(1.5)
        except Exception as err:
            logger.error(f"   -> Error enviando mensaje {m.id}: {err}")


async def repair_prison_break_in_transformers(client: TelegramClient, chat_peer, state: dict):
    """Extrae Prison Break de temas de Transformers y lo mueve al tema canónico de Prison Break (1871)."""
    logger.info("\n--- [1/6] REPARANDO PRISON BREAK EN TRANSFORMERS ---")
    prison_break_topic_id = 1871

    # Detectar temas de Transformers
    transformers_topic_ids = {16869, 18388}
    try:
        res = await client(GetForumTopicsRequest(
            peer=chat_peer,
            offset_date=None,
            offset_id=0,
            offset_topic=0,
            limit=50,
            q="Transformers"
        ))
        for t in getattr(res, "topics", []):
            transformers_topic_ids.add(t.id)
            logger.info(f"   Tema Transformers detectado: '{t.title}' (ID {t.id})")
    except Exception as e:
        logger.warning(f"   Aviso buscando temas de Transformers: {e}")

    pb_messages = []
    logger.info(f"   Buscando mensajes de 'Prison' en el supergrupo...")
    async for msg in client.iter_messages(chat_peer, search="Prison", limit=150):
        top_id = None
        if msg.reply_to:
            top_id = getattr(msg.reply_to, "reply_to_top_id", None) or getattr(msg.reply_to, "reply_to_msg_id", None)
        
        content = extract_text_or_filename(msg)
        if top_id in transformers_topic_ids:
            logger.info(f"   🚨 Mensaje de Prison Break encontrado en Transformers ({top_id}): ID {msg.id} | {content[:60]}")
            pb_messages.append(msg)
        elif top_id == prison_break_topic_id:
            logger.info(f"   ✓ Mensaje ya en Prison Break (1871): ID {msg.id}")
        else:
            logger.info(f"   Mensaje de Prison en tema {top_id}: ID {msg.id} | {content[:60]}")

    logger.info(f"Mensajes de Prison Break mal ubicados en Transformers: {len(pb_messages)}")
    if pb_messages:
        pb_messages.reverse()
        if DRY_RUN:
            logger.info(f"[DRY-RUN] Se moverían {len(pb_messages)} mensajes al tema {prison_break_topic_id}")
        else:
            await forward_or_copy_messages(client, chat_peer, pb_messages, prison_break_topic_id)
            pb_ids = [m.id for m in pb_messages]
            try:
                await client(DeleteMessagesRequest(id=pb_ids))
                logger.info(f"   -> {len(pb_ids)} mensajes eliminados de Transformers")
            except Exception as e:
                logger.warning(f"   -> No se pudieron eliminar de Transformers: {e}")

    # Limpiar alias erróneo en el caché de temas
    topics_cache = state.get("series_topics_cache", {})
    if "serie de tv" in topics_cache:
        del topics_cache["serie de tv"]
        logger.info("   -> Eliminada entrada basura 'serie de tv' del caché de temas")


async def consolidate_series_topics(client: TelegramClient, chat_peer, state: dict, series_name: str, canonical_id: int, stray_topic_ids: list):
    """Consolida episodios dispersos en un solo tema y elimina los temas sobrantes."""
    logger.info(f"\n--- CONSOLIDANDO '{series_name}' (Tema Principal: {canonical_id}) ---")
    
    # Renombrar tema principal al nombre canónico limpio
    if not DRY_RUN:
        try:
            await client(EditForumTopicRequest(
                peer=chat_peer,
                topic_id=canonical_id,
                title=series_name
            ))
            logger.info(f"   -> Tema {canonical_id} renombrado a '{series_name}'")
        except Exception as e:
            logger.info(f"   -> No se requirió renombrado de tema {canonical_id}: {e}")

    # Recorrer temas fragmentados
    for stray_id in stray_topic_ids:
        if stray_id == canonical_id:
            continue
        stray_msgs = []
        try:
            async for msg in client.iter_messages(chat_peer, reply_to=stray_id, limit=50):
                if msg.media:
                    stray_msgs.append(msg)
        except Exception as e:
            logger.warning(f"   -> No se pudieron leer mensajes de tema {stray_id}: {e}")

        logger.info(f"   Tema disperso {stray_id}: {len(stray_msgs)} archivo(s)/video(s) encontrados")
        if stray_msgs:
            stray_msgs.reverse()
            if DRY_RUN:
                logger.info(f"   [DRY-RUN] Se moverían {len(stray_msgs)} mensajes de {stray_id} a {canonical_id}")
            else:
                await forward_or_copy_messages(client, chat_peer, stray_msgs, canonical_id)

        if not DRY_RUN:
            try:
                await client(DeleteTopicHistoryRequest(peer=chat_peer, top_msg_id=stray_id))
                logger.info(f"   🗑️ Tema fragmentado {stray_id} eliminado con éxito")
                await asyncio.sleep(1.0)
            except Exception as e:
                logger.warning(f"   -> No se pudo borrar tema {stray_id}: {e}")


async def purge_junk_topics(client: TelegramClient, chat_peer, state: dict, junk_topic_ids: list):
    """Elimina temas anónimos que fueron creados por error ('2ª temporada', 'audio', etc.)."""
    logger.info(f"\n--- PURGANDO TEMAS BASURA / ANÓNIMOS ---")
    for j_id in junk_topic_ids:
        # Verificar cuántos mensajes tiene
        msgs = []
        try:
            async for m in client.iter_messages(chat_peer, reply_to=j_id, limit=10):
                msgs.append(m)
        except Exception:
            pass

        logger.info(f"   Tema basura {j_id}: {len(msgs)} mensajes")
        if not DRY_RUN:
            try:
                await client(DeleteTopicHistoryRequest(peer=chat_peer, top_msg_id=j_id))
                logger.info(f"   🗑️ Tema basura {j_id} eliminado")
                await asyncio.sleep(1.0)
            except Exception as e:
                logger.warning(f"   -> Error borrando tema basura {j_id}: {e}")


def cleanup_cache_keys(state: dict):
    """Limpia las claves corruptas o fragmentadas en series_topics_cache."""
    logger.info("\n--- LIMPIANDO Y ACTUALIZANDO SERIES_TOPICS_CACHE ---")
    cache = state.get("series_topics_cache", {})
    
    # Lista de claves a eliminar
    keys_to_delete = []
    for k in cache:
        k_low = k.lower()
        if any(bad in k_low for bad in [
            "halcon callejero ", "halcón callejero ",
            "el trueno azul 0", "el trueno azul 1",
            "el amor despu", "el amor despues",
            "entourage-", "entourage the", "entourage meet",
            "temporada", "serie de tv", "serie", "audio", "completas", "leer", "fin 11",
            "libro 1", "libro 2", "libro 3", "sinopsis", "sss", "watch", "falta la"
        ]):
            keys_to_delete.append(k)

    for k in keys_to_delete:
        del cache[k]
        logger.info(f"   - Clave eliminada: '{k}'")

    # Reasignar claves canónicas limpias
    cache["halcon callejero"] = 22068
    cache["halcón callejero"] = 22068
    cache["el trueno azul"] = 19415
    cache["el amor despues del amor"] = 20767
    cache["el amor después del amor"] = 20767
    cache["entourage"] = 21869
    cache["entourage el sequito"] = 21869
    cache["entourage el séquito"] = 21869
    cache["prison break"] = 1871
    cache["transformers"] = 16869

    # Resetear puntero activo para evitar pegado erróneo
    state["current_series_title"] = ""
    state["current_topic_id"] = None
    state["series_topics_cache"] = cache
    logger.info(f"✅ Cache consolidado. Total temas indexados: {len(cache)}")


async def main():
    if not STRING_SESSION:
        logger.error("❌ TELEGRAM_STRING_SESSION no configurada.")
        return

    logger.info("Conectando con Telegram...")
    async with TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH) as client:
        chat_peer = await client.get_entity(SERIES_DEST_CHAT)
        logger.info(f"Supergrupo resuelto: {getattr(chat_peer, 'title', SERIES_DEST_CHAT)}")

        state = load_state()

        # 1. Separar Prison Break de Transformers
        await repair_prison_break_in_transformers(client, chat_peer, state)

        # 2. Halcón Callejero
        halcon_strays = [22071, 22073, 22075, 22077, 22079, 22081, 22083, 22085, 22087, 22089, 22091, 22093]
        await consolidate_series_topics(client, chat_peer, state, "Halcón Callejero", 22068, halcon_strays)

        # 3. El Trueno Azul
        trueno_strays = [19418, 19420, 19422, 19424, 19426, 19428, 19430, 19432, 19434, 19436]
        await consolidate_series_topics(client, chat_peer, state, "El Trueno Azul", 19415, trueno_strays)

        # 4. El Amor Después del Amor
        amor_strays = [20770, 20772, 20775, 20777]
        await consolidate_series_topics(client, chat_peer, state, "El Amor Después del Amor", 20767, amor_strays)

        # 5. Entourage
        entourage_strays = [21968, 21970, 21972, 21974, 21976, 21978, 21980]
        await consolidate_series_topics(client, chat_peer, state, "Entourage (El Séquito)", 21869, entourage_strays)

        # 6. Temas Basura Anónimos
        junk_topics = [
            12219, 12242, 12265, 12288, 12311, 12334, 12357, 12380, 12403, 12425,
            7368, 7369, 7550, 8763, 8942, 9310, 15326, 14992, 19334, 19356, 19378,
            20152, 20727, 20729, 20673, 20547
        ]
        await purge_junk_topics(client, chat_peer, state, junk_topics)

        # 7. Actualizar y guardar estado limpio
        cleanup_cache_keys(state)
        if not DRY_RUN:
            save_state(state)

        logger.info("\n🎉 REPARACIÓN DEL CATÁLOGO DE SERIES FINALIZADA CON ÉXITO")


if __name__ == "__main__":
    asyncio.run(main())
