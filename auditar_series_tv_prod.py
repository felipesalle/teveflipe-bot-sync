import asyncio
import os
import re
import json
from collections import defaultdict
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetForumTopicsRequest

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")

PROD_SERIES = -1004331019870

def extract_base_series_name(file_name):
    if not file_name:
        return ""
    name = re.sub(r'\.(mkv|mp4|avi|ts|m4v)$', '', file_name, flags=re.I)
    name = re.sub(r'@\w+', '', name)
    name = re.sub(r'(?i)\b(?:1080p?|720p?|2160p?|4k|hdtv|x264|x265|hevc|castellano|latino|dual|dvdrip|bluray|web-dl|webrip|amzn)\b', '', name)
    # Separar en temporada o capitulo: s01e01, 1x01, etc.
    parts = re.split(r'(?i)[_\s\.\-]*(?:s\d{1,2}|temporada|\d{1,2}x\d{1,2}|cap[íi]tulo|cap\d+|\b\d{1,2}\.\d{1,2}\b)', name)
    base = parts[0].strip(" .-_#")
    if not base or base.isdigit():
        m = re.search(r'(?i)\d{1,2}x\d{1,2}\s*[-_–]\s*(.+)', name)
        if m:
            base = m.group(1).strip(" .-_#")
        else:
            base = name
    base = re.sub(r'\s+', ' ', base).strip(" .-_")
    return base

async def main():
    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client:
        chat = await client.get_entity(PROD_SERIES)
        print(f"=== AUDITORÍA COMPLETA: {chat.title} ({chat.id}) ===")

        offset_date = None
        offset_id = 0
        offset_topic = 0
        all_topics = []

        print("Recuperando listado completo de temas...")
        while True:
            res = await client(GetForumTopicsRequest(
                peer=chat,
                offset_date=offset_date,
                offset_id=offset_id,
                offset_topic=offset_topic,
                limit=100
            ))
            topics = getattr(res, "topics", [])
            if not topics:
                break
            all_topics.extend(topics)
            print(f"   Recuperados {len(all_topics)} temas...")
            if len(topics) < 100:
                break
            last = topics[-1]
            offset_topic = last.id
            offset_id = last.top_message
            offset_date = last.date
            await asyncio.sleep(0.3)

        print(f"\nTotal temas encontrados en el foro: {len(all_topics)}")

        empty_topics = []
        low_message_topics = [] # 1 o 2 mensajes
        topics_with_messages = []

        for t in all_topics:
            t_id = t.id
            t_title = t.title
            tot_msgs = getattr(t, "total_messages", 0)

            if t_id == 1 or t_title.lower() in ("general", "#general"):
                continue

            if tot_msgs <= 1:
                empty_topics.append({"id": t_id, "title": t_title, "total_messages": tot_msgs})
            elif tot_msgs <= 2:
                low_message_topics.append({"id": t_id, "title": t_title, "total_messages": tot_msgs})
            else:
                topics_with_messages.append({"id": t_id, "title": t_title, "total_messages": tot_msgs})

        print(f"\n📊 RESUMEN INICIAL:")
        print(f"- Temas vacíos (<= 1 mensaje): {len(empty_topics)}")
        print(f"- Temas casi vacíos (2 mensajes): {len(low_message_topics)}")
        print(f"- Temas con contenido (> 2 mensajes): {len(topics_with_messages)}")

        if empty_topics:
            print(f"\n🗑️ TEMAS VACÍOS DETECTADOS ({len(empty_topics)}):")
            for t in empty_topics[:25]:
                print(f"   • Topic {t['id']}: '{t['title']}' (total_msgs={t['total_messages']})")
            if len(empty_topics) > 25:
                print(f"   ... y {len(empty_topics) - 25} temas vacíos más.")

        # 3. Detectar mezclas en temas con contenido
        print(f"\n🔍 ANALIZANDO POSIBLES MEZCLAS EN LOS TEMAS CON CONTENIDO...")
        mixed_topics = []

        # Analizar temas cuyo título sea sospechoso de colisión (palabras cortas como You, The, One, etc.)
        # O temas con muchos mensajes o títulos genéricos
        for idx, t in enumerate(topics_with_messages):
            t_id = t["id"]
            t_title = t["title"]
            tot = t["total_messages"]

            # Si el título es muy corto (<= 4 caracteres) o tiene muchos mensajes (> 80), o es una palabra común:
            # Inspeccionar los mensajes internos
            is_suspicious_candidate = (
                len(t_title.strip()) <= 4 or
                tot >= 70 or
                t_title.lower() in ("the", "it", "one", "him", "her", "we", "us", "see", "all", "now", "lost")
            )

            # Para todos los temas, hagamos un muestreo rápido de 15 mensajes si es sospechoso, o 5 mensajes si es normal
            sample_limit = 25 if is_suspicious_candidate else 6
            
            try:
                distinct_bases = set()
                sample_files = []
                count_sampled = 0

                async for m in client.iter_messages(chat, reply_to=t_id, limit=sample_limit):
                    if m.file:
                        fn = m.file.name or ""
                        sample_files.append(fn)
                        base = extract_base_series_name(fn)
                        if base and len(base) > 2:
                            distinct_bases.add(base.lower())
                    count_sampled += 1

                # Normalizar bases parecidas
                grouped_bases = set()
                for b in distinct_bases:
                    # ignorar diferencias menores
                    b_clean = re.sub(r'[\s_]+', ' ', b).strip()
                    if len(b_clean) >= 3:
                        grouped_bases.add(b_clean)

                if len(grouped_bases) >= 2:
                    # Comprobar si son series verdaderamente distintas o solo variaciones del mismo nombre
                    first_word_set = {b.split()[0] for b in grouped_bases if b.split()}
                    if len(first_word_set) >= 2:
                        mixed_topics.append({
                            "id": t_id,
                            "title": t_title,
                            "total_messages": tot,
                            "detected_series": list(grouped_bases)[:5],
                            "samples": sample_files[:4]
                        })
            except Exception as e:
                pass

            if (idx + 1) % 50 == 0:
                print(f"   Analizados {idx + 1}/{len(topics_with_messages)} temas...")

        print(f"\n==================================================")
        print(f"📊 INFORME DE MEZCLAS DETECTADAS ({len(mixed_topics)} temas sospechosos):")
        print(f"==================================================")
        for m in mixed_topics:
            print(f"⚠️ Topic {m['id']} ('{m['title']}') - Total: {m['total_messages']} msgs")
            print(f"   Series detectadas: {m['detected_series']}")
            print(f"   Archivos muestra: {m['samples']}\n")

        # Guardar reporte JSON
        audit_result = {
            "total_topics": len(all_topics),
            "empty_topics": empty_topics,
            "low_message_topics": low_message_topics,
            "mixed_topics": mixed_topics
        }
        with open("auditoria_produccion_series_tv.json", "w", encoding="utf-8") as f:
            json.dump(audit_result, f, ensure_ascii=False, indent=2)
        print("Reporte guardado en auditoria_produccion_series_tv.json")

if __name__ == "__main__":
    asyncio.run(main())
