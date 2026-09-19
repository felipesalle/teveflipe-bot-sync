import os
import sys
import json
import asyncio
import logging
import re
from collections import defaultdict
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetForumTopicsRequest

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("AuditoriaSeriesTV")

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION", "")
TARGET_CHAT = int(os.getenv("SERIES_DEST_CHAT", "-1002097175258"))

REPORT_FILE = "reporte_auditoria_series_tv.json"


def normalize_for_comparison(title: str) -> str:
    t = title.lower().strip()
    t = re.sub(r"[\[\]\(\)\{\},.+:!¡?¿*=#~_—–-]", " ", t)
    t = re.sub(r"(?i)\b(?:1080p?|720p?|2160p?|4k|hdtv|x264|x265|hevc|castellano|latino|dual|sub|subs|vose|temporada\s*\d+|s\d+|t\d+|\d+x\d+|completa|serie|tv)\b", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def is_suspicious_title(title: str) -> tuple[bool, str]:
    t = title.strip()
    t_low = t.lower()
    
    # Caso 1: Solo números o códigos
    if re.match(r"^\d+$", t) and t not in ("24", "1883", "1923", "300"):
        return True, "Título puramente numérico"
        
    # Caso 2: Código de episodio o temporada aislado
    if re.match(r"(?i)^(?:s\d+(?:e\d+)?|t\d+(?:e\d+)?|\d+x\d+|cap[ií]tulo\s*\d+|episodio\s*\d+|\d+ª?\s*temporada)$", t):
        return True, "Código de temporada o capítulo suelto"
        
    # Caso 3: Empieza por número de episodio (ej: 01 - ..., 02 - ...)
    if re.match(r"^\d{1,3}\s*[-–—.:_]", t) and not any(t.startswith(valid) for valid in ("24 ", "1883 ", "1923 ")):
        return True, "Comienza con número de capítulo (posible fragmentación)"
        
    # Caso 4: Palabras residuales o genéricas
    if t_low in {
        "serie", "series", "serie tv", "serie de tv", "audio", "completas", "leer", "fin",
        "sinopsis", "info", "general", "temporada", "temporadas", "castellano", "latino",
        "falta", "video", "capitulo", "episodio", "watch", "sss"
    }:
        return True, "Palabra genérica o decorativa"
        
    # Caso 5: Demasiado corto y sin letras
    letters = [c for c in t if c.isalpha()]
    if len(letters) < 2 and t not in ("24", "300"):
        return True, "Título con menos de 2 letras"
        
    # Caso 6: Términos de extras / making of
    if re.search(r"(?i)\b(?:making\s*of|deleted\s*scenes?|gag\s*reel|featurette|behind\s*the\s*scenes|bloopers?|trailer)\b", t):
        return True, "Extras o Making-of como tema separado"
        
    return False, ""


async def main():
    if not STRING_SESSION:
        logger.error("❌ TELEGRAM_STRING_SESSION no configurada.")
        return

    logger.info("Conectando con Telegram para auditar todos los temas...")
    async with TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH) as client:
        chat = await client.get_entity(TARGET_CHAT)
        logger.info(f"Supergrupo resuelto: '{chat.title}' (ID: {chat.id})")

        # 1. Recuperar exhaustivamente todos los temas del foro
        offset_date = None
        offset_id = 0
        offset_topic = 0
        all_topics = []

        logger.info("Recuperando listado de temas mediante paginación...")
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
            logger.info(f"   Recuperados {len(all_topics)} temas hasta el momento...")
            if len(topics) < 100:
                break
            last = topics[-1]
            offset_topic = last.id
            offset_id = last.top_message
            offset_date = last.date
            await asyncio.sleep(0.5)

        logger.info(f"\nTotal temas encontrados en el supergrupo: {len(all_topics)}")

        # 2. Analizar títulos y detectar patrones anómalos
        suspicious_list = []
        normalized_map = defaultdict(list)
        topic_info_list = []

        for t in all_topics:
            is_susp, reason = is_suspicious_title(t.title)
            norm = normalize_for_comparison(t.title)
            
            t_data = {
                "id": t.id,
                "title": t.title,
                "top_message": getattr(t, "top_message", None),
                "is_suspicious": is_susp,
                "suspicious_reason": reason,
                "normalized": norm
            }
            topic_info_list.append(t_data)
            
            if is_susp:
                suspicious_list.append(t_data)
                
            if norm and len(norm) >= 3:
                normalized_map[norm].append(t_data)

        # 3. Detectar posibles series fragmentadas en varios temas
        possible_fragmented = {}
        for norm, group in normalized_map.items():
            if len(group) > 1:
                # Verificar si tienen IDs diferentes
                unique_ids = {item["id"] for item in group}
                if len(unique_ids) > 1:
                    possible_fragmented[norm] = group

        # 4. Muestreo de contenido en temas sospechosos y duplicados
        logger.info("\nInspeccionando contenido de temas duplicados/sospechosos para verificar episodios...")
        for norm, group in list(possible_fragmented.items())[:20]:
            for item in group:
                sample_files = []
                try:
                    async for m in client.iter_messages(chat, reply_to=item["id"], limit=5):
                        if m.file and getattr(m.file, "name", None):
                            sample_files.append(m.file.name)
                        elif m.text:
                            sample_files.append(m.text[:50].replace("\n", " "))
                except Exception:
                    pass
                item["sample_files"] = sample_files

        # 5. Generar reporte estructurado
        report = {
            "total_topics": len(all_topics),
            "suspicious_count": len(suspicious_list),
            "fragmented_groups_count": len(possible_fragmented),
            "suspicious_topics": suspicious_list,
            "fragmented_series_groups": possible_fragmented,
            "all_topics_summary": [
                {"id": t["id"], "title": t["title"]} for t in topic_info_list
            ]
        }

        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logger.info(f"\n" + "=" * 60)
        logger.info(f" REPORTE DE AUDITORÍA COMPLETADO")
        logger.info(f"=" * 60)
        logger.info(f"Total Temas Inspeccionados: {len(all_topics)}")
        logger.info(f"Temas con Títulos Sospechosos / Basura: {len(suspicious_list)}")
        logger.info(f"Grupos con Posible Fragmentación / Duplicados: {len(possible_fragmented)}")
        
        if suspicious_list:
            logger.info("\n--- TEMAS SOSPECHOSOS DETECTADOS ---")
            for s in suspicious_list[:30]:
                logger.info(f"  [ID {s['id']}] '{s['title']}' -> Motivo: {s['suspicious_reason']}")
                
        if possible_fragmented:
            logger.info("\n--- SERIES CON MÚLTIPLES TEMAS DETECTADAS ---")
            for norm, group in list(possible_fragmented.items())[:30]:
                logger.info(f"  [Serie: '{norm}'] ({len(group)} temas):")
                for g in group:
                    logger.info(f"     -> ID {g['id']}: '{g['title']}'")

        logger.info(f"\nReporte completo guardado en '{REPORT_FILE}'")


if __name__ == "__main__":
    asyncio.run(main())
