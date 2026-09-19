import os
import sys
import json
import asyncio
import logging
import random
import re
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


async def rename_topic_safe(client: TelegramClient, chat_peer, topic_id: int, new_title: str):
    """Renombra un tema existente en Telegram de forma segura."""
    if DRY_RUN:
        logger.info(f"   [DRY-RUN] Se renombraría tema {topic_id} a '{new_title}'")
        return
    try:
        await client(EditForumTopicRequest(
            peer=chat_peer,
            topic_id=topic_id,
            title=new_title
        ))
        logger.info(f"   🏷️ Tema {topic_id} renombrado con éxito a: '{new_title}'")
        await asyncio.sleep(1.0)
    except Exception as e:
        logger.warning(f"   -> No se pudo renombrar tema {topic_id}: {e}")


async def consolidate_series_topics(client: TelegramClient, chat_peer, series_name: str, canonical_id: int, stray_topic_ids: list):
    """Consolida episodios dispersos en un solo tema y elimina los temas sobrantes."""
    logger.info(f"\n--- CONSOLIDANDO '{series_name}' (Tema Principal: {canonical_id}) ---")
    
    # Renombrar tema principal al nombre canónico limpio
    await rename_topic_safe(client, chat_peer, canonical_id, series_name)

    # Recorrer temas fragmentados
    for stray_id in stray_topic_ids:
        if stray_id == canonical_id:
            continue
        stray_msgs = []
        try:
            async for msg in client.iter_messages(chat_peer, reply_to=stray_id, limit=60):
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


async def inspect_and_rename_topic(client: TelegramClient, chat_peer, topic_id: int, fallback_title: str):
    """Inspecciona los archivos de un tema con nombre corto/raro y le asigna su título correcto."""
    logger.info(f"\n--- INSPECCIONANDO TEMA {topic_id} ('{fallback_title}') ---")
    sample_text = ""
    try:
        async for m in client.iter_messages(chat_peer, reply_to=topic_id, limit=3):
            t = extract_text_or_filename(m)
            if t:
                sample_text = t
                break
    except Exception as e:
        logger.warning(f"Error leyendo tema {topic_id}: {e}")

    logger.info(f"   Muestra de contenido en {topic_id}: {sample_text[:80]}")
    title_to_set = fallback_title
    s_low = sample_text.lower()
    if "sex education" in s_low:
        title_to_set = "Sex Education"
    elif "sex/life" in s_low or "sex life" in s_low:
        title_to_set = "Sex/Life"
    elif "sex and the city" in s_low or "sexo en nueva york" in s_low:
        title_to_set = "Sexo en Nueva York"
    elif "los serrano" in s_low:
        title_to_set = "Los Serrano"

    await rename_topic_safe(client, chat_peer, topic_id, title_to_set)
    return title_to_set


def cleanup_all_cache_keys(state: dict):
    """Limpia exhaustivamente claves fragmentadas y guarda nombres canónicos."""
    logger.info("\n--- CONSOLIDANDO Y ACTUALIZANDO SERIES_TOPICS_CACHE ---")
    cache = state.get("series_topics_cache", {})

    keys_to_delete = []
    for k in cache:
        k_low = k.lower()
        if any(bad in k_low for bad in [
            "constant s01e", "jingking", "peliculasgoogledrive",
            "el consultor 1x", "el consultor (serie)",
            "boardwalk empire - temp", "boardwalk empire temp 2",
            "como conoc", "la brea", "lupin", "ergo proxy", "los pilares", "dracula"
        ]):
            keys_to_delete.append(k)

    for k in keys_to_delete:
        if k in cache:
            del cache[k]
            logger.info(f"   - Clave obsoleta eliminada: '{k}'")

    # Mapeos Canónicos Verificados
    cache["constantine"] = 20349
    cache["el consultor"] = 18857
    cache["boardwalk empire"] = 6746
    cache["como conoci a vuestra madre"] = 8078
    cache["cómo conocí a vuestra madre"] = 8078
    cache["la brea"] = 1596
    cache["lupin"] = 21595
    cache["los pilares de la tierra"] = 11698
    cache["dracula"] = 11797
    cache["drácula"] = 11797
    cache["ergo proxy"] = 6046
    cache["los serrano"] = 20677
    cache["halcon callejero"] = 22068
    cache["halcón callejero"] = 22068
    cache["el trueno azul"] = 19415
    cache["el amor despues del amor"] = 20767
    cache["el amor después del amor"] = 20767
    cache["entourage"] = 21869
    cache["prison break"] = 1871
    cache["transformers"] = 16869

    # Resetear puntero de sesión activa
    state["current_series_title"] = ""
    state["current_topic_id"] = None
    state["series_topics_cache"] = cache
    logger.info(f"✅ Total temas consolidados en caché: {len(cache)}")


async def main():
    if not STRING_SESSION:
        logger.error("❌ TELEGRAM_STRING_SESSION no configurada.")
        return

    logger.info("Conectando con Telegram...")
    async with TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH) as client:
        chat_peer = await client.get_entity(SERIES_DEST_CHAT)
        logger.info(f"Supergrupo resuelto: {getattr(chat_peer, 'title', SERIES_DEST_CHAT)}")

        state = load_state()

        # 1. Constantine (Consolidar 10 episodios en el tema 20349 y borrar los 9 sueltos)
        constantine_strays = [20355, 20357, 20359, 20361, 20363, 20365, 20367, 20369, 20371]
        await consolidate_series_topics(client, chat_peer, "Constantine", 20349, constantine_strays)

        # 2. El Consultor (Consolidar 6 temas sueltos en el tema 18857)
        consultor_strays = [18860, 18862, 18864, 18866, 18868, 18870]
        await consolidate_series_topics(client, chat_peer, "El Consultor", 18857, consultor_strays)

        # 3. Boardwalk Empire (Consolidar 3 temas sueltos de Temp 2 en el tema 6746)
        boardwalk_strays = [6759, 6768, 7331]
        await consolidate_series_topics(client, chat_peer, "Boardwalk Empire", 6746, boardwalk_strays)

        # 4. Cómo Conocí a Vuestra Madre (Consolidar duplicado 8079 en el principal 8078)
        await consolidate_series_topics(client, chat_peer, "Cómo Conocí a Vuestra Madre", 8078, [8079])

        # 5. La Brea (Consolidar duplicado 7773 en el principal 1596)
        await consolidate_series_topics(client, chat_peer, "La Brea", 1596, [7773])

        # 6. Renombrar temas con nombres descriptivos de ripeo o incompletos
        logger.info("\n--- RENOMBRANDO TEMAS A NOMBRES CANÓNICOS LIMPIOS ---")
        await rename_topic_safe(client, chat_peer, 21595, "Lupin")
        await rename_topic_safe(client, chat_peer, 11698, "Los Pilares de la Tierra")
        await rename_topic_safe(client, chat_peer, 11797, "Drácula")
        await rename_topic_safe(client, chat_peer, 6046, "Ergo Proxy")
        await rename_topic_safe(client, chat_peer, 20677, "Los Serrano")

        # Inspeccionar tema 18935 ("Sex")
        await inspect_and_rename_topic(client, chat_peer, 18935, "Sex Education")

        # 7. Limpiar caché de estado persistente y guardar
        cleanup_all_cache_keys(state)
        if not DRY_RUN:
            save_state(state)

        logger.info("\n🎉 CONSOLIDACIÓN Y LIMPIEZA TOTAL DE SERIES TV COMPLETADA EXITOSAMENTE")


if __name__ == "__main__":
    asyncio.run(main())
