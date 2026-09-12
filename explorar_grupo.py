import asyncio
import json
import logging
import os
import sys
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetForumTopicsRequest
from telethon.tl.types import Channel, MessageMediaPhoto, MessageMediaDocument

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("explorar_grupo")

API_ID = int(os.getenv("TELEGRAM_API_ID") or os.getenv("API_ID") or 0)
API_HASH = os.getenv("TELEGRAM_API_HASH") or os.getenv("API_HASH") or ""
STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION") or ""

TARGET_CHAT_ID = int(os.getenv("TARGET_CHAT_ID", "-1002160549536"))


async def explore_group():
    if not STRING_SESSION:
        logger.error("TELEGRAM_STRING_SESSION no configurada.")
        return

    logger.info(f"Conectando a Telegram para explorar el chat: {TARGET_CHAT_ID}...")
    async with TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH) as client:
        try:
            entity = await client.get_entity(TARGET_CHAT_ID)
        except Exception as e:
            logger.error(f"No se pudo obtener la entidad {TARGET_CHAT_ID}: {e}")
            return

        chat_title = getattr(entity, "title", "Desconocido")
        chat_username = getattr(entity, "username", None)
        is_forum = getattr(entity, "forum", False)
        is_megagroup = getattr(entity, "megagroup", False)
        is_channel = getattr(entity, "broadcast", False)

        logger.info("=" * 60)
        logger.info(f"CHAT ENCONTRADO: {chat_title}")
        logger.info(f"ID: {TARGET_CHAT_ID}")
        logger.info(f"Username: @{chat_username}" if chat_username else "Username: (Privado/Sin username)")
        logger.info(f"Tipo: Forum={is_forum}, Megagroup={is_megagroup}, BroadcastChannel={is_channel}")
        logger.info("=" * 60)

        report = {
            "chat_id": TARGET_CHAT_ID,
            "titulo": chat_title,
            "username": chat_username,
            "es_foro": is_forum,
            "es_megagrupo": is_megagroup,
            "es_canal": is_channel,
            "temas": [],
            "series": []
        }

        # Caso 1: Es un grupo con Temas / Foro
        if is_forum:
            logger.info("El grupo es un FORO. Obteniendo lista de temas...")
            all_topics = []
            offset_date = None
            offset_id = 0
            offset_topic = 0

            input_peer = await client.get_input_entity(entity)

            while True:
                res = await client(GetForumTopicsRequest(
                    peer=input_peer,
                    offset_date=offset_date,
                    offset_id=offset_id,
                    offset_topic=offset_topic,
                    limit=100
                ))
                if not res.topics:
                    break
                for t in res.topics:
                    topic_id = getattr(t, "id", None)
                    topic_title = getattr(t, "title", "Sin título")
                    top_msg_id = getattr(t, "top_message", 0)
                    all_topics.append({
                        "id": topic_id,
                        "titulo": topic_title,
                        "top_message": top_msg_id
                    })
                if len(res.topics) < 100:
                    break
                last_t = res.topics[-1]
                offset_topic = last_t.id
                offset_id = last_t.top_message
                offset_date = None

            logger.info(f"Total de temas encontrados: {len(all_topics)}")

            # Para cada tema, contar cuántos archivos de video o mensajes hay
            for idx, top in enumerate(all_topics, 1):
                t_id = top["id"]
                t_title = top["titulo"]
                video_count = 0
                sample_files = []
                try:
                    async for m in client.iter_messages(entity, reply_to=t_id, limit=80):
                        fname = None
                        if m.media and hasattr(m.media, "document") and m.media.document:
                            for attr in m.media.document.attributes:
                                if hasattr(attr, "file_name") and attr.file_name:
                                    fname = attr.file_name
                                    break
                            if fname or (m.media.document.mime_type and "video" in m.media.document.mime_type):
                                video_count += 1
                                if len(sample_files) < 3 and fname:
                                    sample_files.append(fname)
                except Exception as ex:
                    logger.warning(f"Error leyendo tema {t_id} ({t_title}): {ex}")

                top["video_count"] = video_count
                top["sample_files"] = sample_files
                logger.info(f"[{idx}/{len(all_topics)}] Tema: '{t_title}' (ID: {t_id}) - Videos: {video_count}")

            report["temas"] = all_topics

            # Generar Markdown
            with open("EXPLORACION_GRUPO.md", "w", encoding="utf-8") as f:
                f.write(f"# 📂 Catálogo del Grupo: **{chat_title}**\n\n")
                f.write(f"- **ID del Chat:** `{TARGET_CHAT_ID}`\n")
                f.write(f"- **Tipo:** Grupo con Foros/Temas habilitados\n")
                f.write(f"- **Total de Temas (Series):** {len(all_topics)}\n\n")
                f.write("| # | Nombre del Tema / Serie | ID Tema | Cantidad de Videos | Archivos de Muestra |\n")
                f.write("|---|------------------------|---------|--------------------|---------------------|\n")
                for i, t in enumerate(all_topics, 1):
                    samples = "<br>".join(f"`{s}`" for s in t.get("sample_files", []))
                    f.write(f"| {i} | **{t['titulo']}** | `{t['id']}` | {t.get('video_count', 0)} | {samples} |\n")

        # Caso 2: Es un canal o grupo normal (sin foros)
        else:
            logger.info("El chat NO es un foro. Escaneando mensajes recientes para ver contenido...")
            recent_msgs = []
            async for m in client.iter_messages(entity, limit=200):
                fname = None
                if m.media and hasattr(m.media, "document") and m.media.document:
                    for attr in m.media.document.attributes:
                        if hasattr(attr, "file_name") and attr.file_name:
                            fname = attr.file_name
                            break
                text = (m.text or "").replace("\n", " ")[:60]
                recent_msgs.append({
                    "id": m.id,
                    "date": str(m.date),
                    "file_name": fname,
                    "text": text
                })

            report["mensajes_recientes"] = recent_msgs[:50]

            with open("EXPLORACION_GRUPO.md", "w", encoding="utf-8") as f:
                f.write(f"# 📂 Catálogo del Grupo: **{chat_title}**\n\n")
                f.write(f"- **ID del Chat:** `{TARGET_CHAT_ID}`\n")
                f.write(f"- **Tipo:** Canal / Grupo estándar (sin foros)\n")
                f.write(f"- **Mensajes analizados:** {len(recent_msgs)}\n\n")
                f.write("| ID Msg | Archivo / Nombre | Descripción |\n")
                f.write("|--------|-------------------|-------------|\n")
                for m in recent_msgs[:50]:
                    f.write(f"| `{m['id']}` | `{m.get('file_name') or 'N/A'}` | {m.get('text') or ''} |\n")

        with open("exploracion_grupo.json", "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logger.info("Exploración finalizada con éxito. Guardado en EXPLORACION_GRUPO.md")


if __name__ == "__main__":
    asyncio.run(explore_group())
