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

def clean_series_name(file_name):
    if not file_name:
        return ""
    name = re.sub(r'\.(mkv|mp4|avi|ts|m4v)$', '', file_name, flags=re.I)
    name = re.sub(r'@\w+', '', name)
    name = re.sub(r'(?i)\b(?:1080p?|720p?|2160p?|4k|hdtv|x264|x265|hevc|castellano|latino|dual|dvdrip|bluray|web-dl|webrip|amzn)\b', '', name)
    parts = re.split(r'(?i)[_\s\.\-]*(?:s\d{1,2}|temporada|\d{1,2}x\d{1,2}|cap[íi]tulo|cap\d+|\b\d{1,2}\.\d{1,2}\b)', name)
    base = parts[0].strip(" .-_#")
    if not base or base.isdigit():
        m = re.search(r'(?i)\d{1,2}x\d{1,2}\s*[-_–]\s*(.+)', name)
        if m:
            base = m.group(1).strip(" .-_#")
        else:
            base = name
    base = re.sub(r'[\s_]+', ' ', base).strip(" .-_")
    return base

async def main():
    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client:
        chat = await client.get_entity(PROD_SERIES)
        print(f"=== AUDITORÍA COMPLETA: {chat.title} ({chat.id}) ===")

        offset_date = None
        offset_id = 0
        offset_topic = 0
        all_topics = []

        print("Recuperando todos los temas del foro...")
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
            if len(topics) < 100:
                break
            last = topics[-1]
            offset_topic = last.id
            offset_id = last.top_message
            offset_date = last.date
            await asyncio.sleep(0.3)

        print(f"Total temas en el supergrupo: {len(all_topics)}")

        empty_topics = []
        active_topics = []

        for t in all_topics:
            if t.id == 1 or t.title.lower() in ("general", "#general"):
                continue
            
            # Si top_message == id, el tema no tiene ningún mensaje posterior a su creación
            if t.top_message == t.id:
                empty_topics.append({"id": t.id, "title": t.title})
            else:
                active_topics.append({"id": t.id, "title": t.title, "top_message": t.top_message})

        print(f"\n📊 RESUMEN:")
        print(f"- Temas Vacíos (0 mensajes): {len(empty_topics)}")
        print(f"- Temas Activos (con contenido): {len(active_topics)}")

        if empty_topics:
            print(f"\n🗑️ LISTA DE TEMAS VACÍOS ({len(empty_topics)}):")
            for t in empty_topics:
                print(f"   • ID {t['id']}: '{t['title']}'")

        # Inspeccionar cada tema activo para detectar posibles mezclas
        print(f"\n🔍 INSPECCIONANDO CONTENIDO DE LOS {len(active_topics)} TEMAS ACTIVOS...")
        mixed_topics = []
        single_episode_topics = []

        for idx, t in enumerate(active_topics):
            t_id = t["id"]
            t_title = t["title"]
            
            # Obtener mensajes del tema (hasta 40 mensajes de muestra)
            msgs = []
            files = []
            async for m in client.iter_messages(chat, reply_to=t_id, limit=40):
                msgs.append(m)
                if m.file:
                    fn = m.file.name or ""
                    files.append(fn)

            total_sample = len(msgs)
            if total_sample <= 1:
                single_episode_topics.append({"id": t_id, "title": t_title, "file": files[0] if files else "Sin archivo"})

            # Detectar series distintas en los nombres de archivo
            series_bases = defaultdict(int)
            for fn in files:
                base = clean_series_name(fn)
                if base:
                    # Normalizar a minúsculas y quitar caracteres raros
                    base_key = re.sub(r'[^a-zA-Z0-9áéíóúÁÉÍÓÚñÑ ]', '', base).strip().lower()
                    if len(base_key) >= 3:
                        series_bases[base_key] += 1

            # Si encontramos más de 1 serie con nombres claramente distintos:
            if len(series_bases) >= 2:
                # Filtrar si solo son variaciones de la misma serie (ej: "you" y "you s04")
                first_words = {k.split()[0] for k in series_bases.keys() if k.split()}
                if len(first_words) >= 2:
                    mixed_topics.append({
                        "id": t_id,
                        "title": t_title,
                        "total_sampled": total_sample,
                        "detected_series": dict(series_bases),
                        "sample_files": files[:5]
                    })

            if (idx + 1) % 25 == 0 or (idx + 1) == len(active_topics):
                print(f"   Analizados {idx + 1}/{len(active_topics)} temas...")

        print(f"\n==================================================")
        print(f"⚠️ TEMAS CON MEZCLAS DETECTADOS: {len(mixed_topics)}")
        print(f"==================================================")
        for m in mixed_topics:
            print(f"📌 Topic {m['id']}: '{m['title']}' (Muestra: {m['total_sampled']} archivos)")
            print(f"   Series encontradas: {m['detected_series']}")
            print(f"   Ejemplos de archivos: {m['sample_files']}\n")

        # Guardar reporte
        report = {
            "total_topics": len(all_topics),
            "empty_topics_count": len(empty_topics),
            "empty_topics": empty_topics,
            "active_topics_count": len(active_topics),
            "mixed_topics_count": len(mixed_topics),
            "mixed_topics": mixed_topics,
            "single_episode_topics": single_episode_topics
        }
        with open("auditoria_series_tv_prod_final.json", "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print("\n✅ Auditoría completa guardada en auditoria_series_tv_prod_final.json")

if __name__ == "__main__":
    asyncio.run(main())
