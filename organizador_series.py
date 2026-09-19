#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
organizador_series.py
Organizador y sincronizador inteligente de series para Telegram y TeveFlipe.
Agrupa automáticamente episodios bajo su serie canónica usando la API de TMDb.
"""

import os
import sys
import re
import json
import asyncio
import logging
import urllib.parse
from typing import Optional, Tuple, Dict, List, Any
from collections import defaultdict

import urllib.request
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.types import (
    MessageMediaDocument,
    DocumentAttributeVideo,
    DocumentAttributeFilename,
)
from telethon.tl.functions.messages import (
    GetForumTopicsRequest,
    ForwardMessagesRequest,
    CreateForumTopicRequest,
)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("OrganizadorSeries")

# Configuración de Telegram
API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION", "")

SERIES_SOURCE_CHAT = int(os.getenv("SERIES_SOURCE_CHAT", "-1002257262928"))
SERIES_SOURCE_TOPIC = int(os.getenv("SERIES_SOURCE_TOPIC", "157592"))
SERIES_DEST_CHAT = int(os.getenv("SERIES_DEST_CHAT", "-1002097175258"))

TMDB_API_KEY = os.getenv("TMDB_API_KEY", "2b7cd7b237fe99884613b230a910a09c")
TMDB_CACHE_FILE = "tmdb_series_cache.json"

VIDEO_EXTENSIONS = (".mkv", ".mp4", ".avi", ".mov", ".webm", ".ts", ".m4v")

# -----------------------------------------------------------------------------
# 1. Limpieza Previa de Ruido (Sanitización)
# -----------------------------------------------------------------------------
TECH_NOISE_REGEX = re.compile(
    r"(?i)\b(?:1080p?|720p?|4k|2160p?|480p?|576p?|x264|x265|hevc|h264|h265|web-?dl|webrip|bluray|bdrip|dvdrip|hdtv|ac3|aac|dts|dual|castellano|latino|spanish|spa|vose|sub(?:s|titulado)?|rip|repack|proper)\b"
)
BRACKET_REGEX = re.compile(r"\[.*?\]|\(.*?\)")
SPECIAL_CHARS_REGEX = re.compile(r"[._\-–—]+")


def sanitize_raw_title(raw_text: str) -> str:
    """Elimina etiquetas técnicas habituales, canales de telegram, corchetes y normaliza espacios."""
    # Quitar extensiones de video si existen
    for ext in VIDEO_EXTENSIONS:
        if raw_text.lower().endswith(ext):
            raw_text = raw_text[:-len(ext)]
            break

    # Quitar menciones a canales (@canal, @la_comunidad, @locosxelcine, etc.)
    text = re.sub(r"@\w+", "", raw_text)
    # Quitar corchetes de fansubs y grupos [xxx]
    text = re.sub(r"\[.*?\]", "", text)
    # Quitar ruido técnico habitual
    text = TECH_NOISE_REGEX.sub(" ", text)
    # Reemplazar puntos y guiones bajos por espacios
    text = re.sub(r"[._]+", " ", text)
    # Limpiar espacios repetidos
    return re.sub(r"\s+", " ", text).strip()


# -----------------------------------------------------------------------------
# 2. Extractor de Nombre y Episodio en Cascada (5 Patrones)
# -----------------------------------------------------------------------------
def parse_raw_filename(filename: str) -> Tuple[Optional[str], int, int]:
    """
    Evalúa en cascada 5 patrones de nombrado de series.
    Retorna: (titulo_candidato, temporada, episodio)
    """
    # Quitar extensión primero
    base_name = filename
    for ext in VIDEO_EXTENSIONS:
        if base_name.lower().endswith(ext):
            base_name = base_name[:-len(ext)]
            break

    # Patrón 0: Temporada y Episodio al INICIO ('2x10 Un lugar para soñar' o 'S02E10 Un lugar para soñar')
    p0 = re.search(
        r"^(?:[Ss](\d+)[._\s]*[Ee](\d+)|\b(\d{1,2})x(\d{1,2})\b)[._\s-]+(.*?)$",
        base_name,
        re.IGNORECASE
    )
    if p0:
        s_num = int(p0.group(1) or p0.group(3) or 1)
        e_num = int(p0.group(2) or p0.group(4) or 1)
        cand = sanitize_raw_title(p0.group(5))
        if cand and len(cand) >= 2:
            return cand, s_num, e_num

    # Patrón 1: Estándar S01E01 o 1x01 en el medio/final
    # ^(.*?)[._\s]+(?:[Ss](\d+)[._\s]*[Ee](\d+)|\b(\d{1,2})x(\d{1,2})\b)(.*)$
    p1 = re.search(
        r"^(.*?)[._\s]+(?:[Ss](\d+)[._\s]*[Ee](\d+)|\b(\d{1,2})x(\d{1,2})\b)(.*)$",
        base_name,
        re.IGNORECASE
    )
    if p1:
        cand = sanitize_raw_title(p1.group(1))
        s_num = int(p1.group(2) or p1.group(4) or 1)
        e_num = int(p1.group(3) or p1.group(5) or 1)
        if cand and len(cand) >= 2:
            return cand, s_num, e_num

    # Patrón 1b: Códigos numéricos de 3 o 4 dígitos ('Chicago Fire - 815' -> T8 E15, '1022' -> T10 E22)
    p1b = re.search(r"^(.*?)[._\s]+-[._\s]+(\d{3,4})(?:[._\s]+.*)?$", base_name)
    if p1b:
        cand = sanitize_raw_title(p1b.group(1))
        digits = p1b.group(2)
        if len(digits) == 3:
            s_num = int(digits[0])
            e_num = int(digits[1:])
        else:
            s_num = int(digits[:2])
            e_num = int(digits[2:])
        if cand and len(cand) >= 2:
            return cand, s_num, e_num

    # Patrón 2: Palabra Capítulo al final o medio
    # ^(.*?)[._\s]+(?:capítulo|cap|episodio|ep)[._\s-]*(\d+)(.*)$
    p2 = re.search(
        r"^(.*?)[._\s]+(?:cap[íi]tulo|cap|episodio|ep)[._\s-]*(\d+)(.*)$",
        base_name,
        re.IGNORECASE
    )
    if p2:
        cand = sanitize_raw_title(p2.group(1))
        e_num = int(p2.group(2))
        if cand and len(cand) >= 2:
            return cand, 1, e_num

    # Patrón 3: Número al inicio ('01 - Serie', '01. Serie', '01º Serie', '1º Serie')
    # ^(\d{1,3})[._\sºª-]+(.*?)$
    p3 = re.search(r"^(\d{1,3})[._\sºª-]+(.*?)$", base_name)
    if p3:
        e_num = int(p3.group(1))
        cand = sanitize_raw_title(p3.group(2))
        if cand and len(cand) >= 2:
            return cand, 1, e_num

    # Patrón 4: Palabra Capítulo al inicio ('Capitulo 1 - Serie')
    # ^(?:capítulo|cap|ep)[._\s-]*(\d+)[._\s-]+(.*?)$
    p4 = re.search(
        r"^(?:cap[íi]tulo|cap|ep)[._\s-]*(\d+)[._\s-]+(.*?)$",
        base_name,
        re.IGNORECASE
    )
    if p4:
        e_num = int(p4.group(1))
        cand = sanitize_raw_title(p4.group(2))
        if cand and len(cand) >= 2:
            return cand, 1, e_num

    # Patrón 5: Anime simple ('Serie - 01' o 'Serie 01')
    # ^(.*?)[._\s]+-[._\s]+(\d{1,3})(?:[._\s]+.*)?$
    p5 = re.search(r"^(.*?)[._\s]+-[._\s]+(\d{1,3})(?:[._\s]+.*)?$", base_name)
    if p5:
        cand = sanitize_raw_title(p5.group(1))
        e_num = int(p5.group(2))
        if cand and len(cand) >= 2:
            return cand, 1, e_num

    # Fallback: Sanitizar nombre base
    fallback = sanitize_raw_title(base_name)
    return (fallback if len(fallback) >= 2 else None), 1, 1


# -----------------------------------------------------------------------------
# 3. Normalizador Universal con la API de TMDb
# -----------------------------------------------------------------------------
class TmdbNormalizer:
    def __init__(self, api_key: str, cache_file: str = TMDB_CACHE_FILE):
        self.api_key = api_key
        self.cache_file = cache_file
        self.cache: Dict[str, Optional[str]] = {}
        self._load_cache()

    def _load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
            except Exception as e:
                logger.warning(f"No se pudo cargar caché TMDb: {e}")

    def save_cache(self):
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"No se pudo guardar caché TMDb: {e}")

    def normalize(self, candidate_title: str) -> str:
        """Consulta TMDb para obtener el título canónico oficial en español."""
        if not candidate_title:
            return "Desconocido"

        key = candidate_title.strip().lower()
        if key in self.cache:
            return self.cache[key] or candidate_title.strip().title()

        # Si el título candidato tiene ruido o longitud insuficiente, evitar consulta innecesaria
        if len(key) < 3 or key.isdigit():
            self.cache[key] = candidate_title.strip().title()
            return self.cache[key]

        try:
            encoded_query = urllib.parse.quote(candidate_title.strip())
            url = f"https://api.themoviedb.org/3/search/tv?api_key={self.api_key}&query={encoded_query}&language=es-ES"
            req = urllib.request.Request(url, headers={"User-Agent": "TeveFlipeSyncBot/2.0"})
            with urllib.request.urlopen(req, timeout=6) as response:
                data = json.loads(response.read().decode("utf-8"))
                results = data.get("results", [])
                if results and len(results) > 0:
                    canonical_name = results[0].get("name") or results[0].get("original_name")
                    if canonical_name:
                        canonical_clean = canonical_name.strip()
                        self.cache[key] = canonical_clean
                        return canonical_clean

        except Exception as e:
            logger.debug(f"Error consultando TMDb para '{candidate_title}': {e}")

        # Fallback si no hay resultado en TMDb
        fallback_name = candidate_title.strip().title()
        self.cache[key] = fallback_name
        return fallback_name


# -----------------------------------------------------------------------------
# Detección y Extracción de Archivos de Video en Telegram
# -----------------------------------------------------------------------------
def is_video_message(message) -> bool:
    if not message.media:
        return False
    if getattr(message, "video", None):
        return True
    if isinstance(message.media, MessageMediaDocument):
        doc = message.media.document
        if doc:
            if doc.mime_type and doc.mime_type.startswith("video/"):
                return True
            for attr in getattr(doc, "attributes", []):
                if isinstance(attr, DocumentAttributeVideo):
                    return True
                if isinstance(attr, DocumentAttributeFilename):
                    if attr.file_name and attr.file_name.lower().endswith(VIDEO_EXTENSIONS):
                        return True
    return False


def get_message_filename(message) -> str:
    if message.file and hasattr(message.file, "name") and message.file.name:
        return message.file.name
    if isinstance(message.media, MessageMediaDocument) and message.media.document:
        for attr in getattr(message.media.document, "attributes", []):
            if isinstance(attr, DocumentAttributeFilename) and attr.file_name:
                return attr.file_name
    return message.text or f"video_{message.id}.mp4"


# -----------------------------------------------------------------------------
# Lógica Principal: Análisis (Fase 1) y Sincronización (Fase 2)
# -----------------------------------------------------------------------------
async def analizar_canal_origen(client: TelegramClient, tmdb: TmdbNormalizer) -> Tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]:
    """Escanea el canal origen y clasifica todos los archivos de video en series canónicas."""
    min_id = int(os.getenv("SERIES_MIN_ID", "157000"))
    logger.info(f"Iniciando escaneo del canal origen: chat {SERIES_SOURCE_CHAT}, topic {SERIES_SOURCE_TOPIC}, min_id {min_id}...")
    source_entity = await client.get_entity(SERIES_SOURCE_CHAT)

    raw_candidates_dict: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    dudosos: List[Dict[str, Any]] = []

    total_scanned = 0
    total_videos = 0

    async for msg in client.iter_messages(
        source_entity,
        reply_to=SERIES_SOURCE_TOPIC if SERIES_SOURCE_TOPIC else None,
        min_id=min_id,
        limit=None,
        reverse=True
    ):
        total_scanned += 1
        if total_scanned % 1000 == 0:
            logger.info(f"   Escaneados {total_scanned} mensajes ({total_videos} videos encontrados)...")

        if not is_video_message(msg):
            continue

        total_videos += 1
        raw_name = get_message_filename(msg)
        caption = msg.text or ""

        # Intentar parsear el nombre del archivo
        cand_title, season, episode = parse_raw_filename(raw_name)

        # Si el nombre del archivo no dio título, probar con el pie de foto
        if not cand_title and caption:
            cand_title, season, episode = parse_raw_filename(caption)

        if not cand_title or len(cand_title) < 2:
            dudosos.append({
                "message_id": msg.id,
                "file_name": raw_name,
                "caption": caption,
                "reason": "No se pudo extraer un título de serie válido"
            })
            continue

        raw_candidates_dict[cand_title].append({
            "message_id": msg.id,
            "raw_filename": raw_name,
            "season": season,
            "episode": episode,
            "date": str(msg.date)
        })

    logger.info(f"Escaneo inicial finalizado: {total_scanned} msgs | {total_videos} videos | {len(raw_candidates_dict)} títulos preliminares.")

    # 2. Normalizar títulos únicos con TMDb (rápido y sin peticiones repetidas)
    logger.info(f"Normalizando {len(raw_candidates_dict)} series únicas con la API de TMDb...")
    series_dict: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for i, (cand_title, eps) in enumerate(raw_candidates_dict.items(), 1):
        canonical_series = tmdb.normalize(cand_title)
        series_dict[canonical_series].extend(eps)
        if i % 15 == 0 or i == len(raw_candidates_dict):
            logger.info(f"   Normalizadas {i}/{len(raw_candidates_dict)} series con TMDb...")

    # Guardar caché de TMDb actualizado
    tmdb.save_cache()

    logger.info(f"Normalización completada. Total series canónicas únicas: {len(series_dict)}.")
    return series_dict, dudosos


def imprimir_y_guardar_reporte(series_dict: Dict[str, List[Dict[str, Any]]], dudosos: List[Dict[str, Any]]):
    """Muestra el resumen en pantalla y genera archivos de reporte para revisión."""
    total_archivos = sum(len(eps) for eps in series_dict.values()) + len(dudosos)
    total_series = len(series_dict)

    print("\n" + "=" * 60)
    print("📊 ANÁLISIS DE SERIES COMPLETADO")
    print(f"Total archivos de vídeo leídos: {total_archivos}")
    print(f"Total series únicas identificadas: {total_series}")
    print("-" * 60)

    # Ordenar series por cantidad de capítulos descendente
    series_ordenadas = sorted(series_dict.items(), key=lambda item: len(item[1]), reverse=True)

    for serie, episodios in series_ordenadas:
        temporadas = set(ep["season"] for ep in episodios)
        print(f"📁 \"{serie}\" ➔ {len(episodios)} capítulos ({len(temporadas)} temp)")

    if dudosos:
        print("-" * 60)
        print(f"⚠️ Sin clasificar / Dudosos: {len(dudosos)} archivos (guardados en 'dudosos.txt')")
    print("=" * 60 + "\n")

    # Guardar propuesta en JSON
    propuesta = {
        "total_archivos": total_archivos,
        "total_series": total_series,
        "series": {
            serie: {
                "total_capitulos": len(eps),
                "temporadas": sorted(list(set(e["season"] for e in eps))),
                "capitulos": sorted(eps, key=lambda x: (x["season"], x["episode"]))
            }
            for serie, eps in series_ordenadas
        },
        "dudosos_count": len(dudosos)
    }

    with open("propuesta_series_tv.json", "w", encoding="utf-8") as f:
        json.dump(propuesta, f, indent=2, ensure_ascii=False)

    # Guardar dudosos en dudosos.txt
    with open("dudosos.txt", "w", encoding="utf-8") as f:
        for d in dudosos:
            f.write(f"ID: {d['message_id']} | Archivo: {d['file_name']} | Caption: {d['caption']}\n")

    # Guardar reporte Markdown legible
    with open("PROPUESTA_SERIES_TV.md", "w", encoding="utf-8") as f:
        f.write("# 📺 Propuesta de Sincronización de Series TV\n\n")
        f.write(f"- **Total archivos analizados:** {total_archivos}\n")
        f.write(f"- **Series únicas identificadas:** {total_series}\n")
        f.write(f"- **Archivos dudosos/no identificados:** {len(dudosos)}\n\n")
        f.write("| # | Serie Canónica (TMDb) | Capítulos | Temporadas | Ejemplo de Archivo |\n")
        f.write("|---|---|---|---|---|\n")
        for i, (serie, eps) in enumerate(series_ordenadas, 1):
            temps = ",".join(str(t) for t in sorted(list(set(e["season"] for e in eps))))
            ejemplo = eps[0]["raw_filename"][:45] if eps else ""
            f.write(f"| {i} | **{serie}** | {len(eps)} | T{temps} | `{ejemplo}` |\n")


async def sincronizar_telegram(
    client: TelegramClient,
    series_dict: Dict[str, List[Dict[str, Any]]],
    series_whitelist: Optional[List[str]] = None
):
    """Crea los temas en el supergrupo destino si no existen y reenvía los episodios ordenados."""
    dest_entity = await client.get_entity(SERIES_DEST_CHAT)
    source_entity = await client.get_entity(SERIES_SOURCE_CHAT)

    logger.info(f"Conectado a supergrupo destino: '{getattr(dest_entity, 'title', SERIES_DEST_CHAT)}'...")

    # 1. Obtener todos los temas existentes en el supergrupo destino para evitar duplicados
    existing_topics: Dict[str, int] = {}
    offset_date = None
    offset_id = 0
    offset_topic = 0

    logger.info("Recuperando temas existentes en el foro para no duplicar...")
    while True:
        res = await client(GetForumTopicsRequest(
            peer=dest_entity,
            offset_date=offset_date,
            offset_id=offset_id,
            offset_topic=offset_topic,
            limit=100
        ))
        topics = getattr(res, "topics", [])
        if not topics:
            break
        for top in topics:
            title_clean = getattr(top, "title", "").strip().lower()
            existing_topics[title_clean] = getattr(top, "id")

        if len(topics) < 100:
            break
        last_t = topics[-1]
        offset_topic = getattr(last_t, "id", 0)
        offset_id = getattr(last_t, "top_message", 0)
        offset_date = getattr(last_t, "date", None)

    logger.info(f"Temas existentes en destino: {len(existing_topics)}.")

    # 2. Filtrar si se especificó una lista blanca
    series_to_process = series_dict
    if series_whitelist:
        norm_white = set(w.strip().lower() for w in series_whitelist)
        series_to_process = {k: v for k, v in series_dict.items() if k.strip().lower() in norm_white}
        logger.info(f"Filtro aplicado: {len(series_to_process)} de {len(series_dict)} series seleccionadas.")

    for serie_name, eps in series_to_process.items():
        serie_key = serie_name.strip().lower()
        topic_id = existing_topics.get(serie_key)

        # Si el tema no existe, crearlo
        if not topic_id:
            logger.info(f"🆕 Creando nuevo Tema en el foro: '{serie_name}'...")
            try:
                created = await client(CreateForumTopicRequest(
                    peer=dest_entity,
                    title=serie_name[:128]
                ))
                for update in getattr(created, "updates", []):
                    msg = getattr(update, "message", None)
                    if msg and hasattr(msg, "id"):
                        topic_id = msg.id
                        break
                    elif hasattr(update, "id"):
                        topic_id = update.id

                if topic_id:
                    existing_topics[serie_key] = topic_id
                    logger.info(f"   ✓ Tema creado exitosamente (Topic ID: {topic_id})")
                    await asyncio.sleep(1.0)
                else:
                    logger.error(f"No se pudo obtener el ID del tema creado para '{serie_name}'. Omitiendo.")
                    continue
            except errors.FloodWaitError as e:
                logger.warning(f"FloodWait creando tema: esperando {e.seconds + 2}s...")
                await asyncio.sleep(e.seconds + 2)
            except Exception as e:
                logger.error(f"Error creando tema para '{serie_name}': {e}")
                continue
        else:
            logger.info(f"📌 Tema existente encontrado para '{serie_name}' (Topic ID: {topic_id})")

        # 3. Reenviar los episodios ordenados cronológicamente por Temporada y Episodio
        sorted_eps = sorted(eps, key=lambda x: (x["season"], x["episode"], x["message_id"]))
        msg_ids = [e["message_id"] for e in sorted_eps]

        logger.info(f"Reenviando {len(msg_ids)} episodios al tema '{serie_name}' (ID {topic_id})...")

        # Reenviar en lotes de 10 o individualmente con drop_author=True
        for i in range(0, len(msg_ids), 10):
            chunk = msg_ids[i:i + 10]
            success = False
            while not success:
                try:
                    await client(ForwardMessagesRequest(
                        from_peer=source_entity,
                        to_peer=dest_entity,
                        id=chunk,
                        drop_author=True,
                        top_msg_id=topic_id
                    ))
                    success = True
                    await asyncio.sleep(1.8)
                except errors.FloodWaitError as e:
                    logger.warning(f"FloodWait al reenviar: esperando {e.seconds + 2}s...")
                    await asyncio.sleep(e.seconds + 2)
                except Exception as e:
                    logger.warning(f"Fallo en lote ({e}). Intentando reenvío individual...")
                    for single_id in chunk:
                        try:
                            await client(ForwardMessagesRequest(
                                from_peer=source_entity,
                                to_peer=dest_entity,
                                id=[single_id],
                                drop_author=True,
                                top_msg_id=topic_id
                            ))
                            await asyncio.sleep(1.8)
                        except Exception as ex_single:
                            logger.error(f"Error reenviando mensaje {single_id}: {ex_single}")
                    success = True

        logger.info(f"✅ Serie '{serie_name}' completada ({len(msg_ids)} capítulos).")

    logger.info("🎉 Sincronización completada exitosamente.")


# -----------------------------------------------------------------------------
# Punto de Entrada
# -----------------------------------------------------------------------------
async def main():
    if not STRING_SESSION:
        logger.error("❌ TELEGRAM_STRING_SESSION no configurada en las variables de entorno.")
        return

    tmdb = TmdbNormalizer(api_key=TMDB_API_KEY)

    logger.info("Conectando con Telegram...")
    async with TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH) as client:
        # FASE 1: Análisis y Resumen
        series_dict, dudosos = await analizar_canal_origen(client, tmdb)
        imprimir_y_guardar_reporte(series_dict, dudosos)

        # Si se ejecuta con flag automático --execute, o interactivo si hay TTY
        auto_execute = "--execute" in sys.argv
        is_interactive = sys.stdin.isatty()

        proceder = False
        if auto_execute:
            proceder = True
        elif is_interactive:
            try:
                resp = input("¿Deseas proceder a crear los temas y reenviar los capítulos? (s/n): ")
                proceder = resp.strip().lower() in ("s", "si", "y", "yes")
            except (EOFError, KeyboardInterrupt):
                proceder = False

        if not proceder:
            logger.info("🛑 Fase 1 completada. No se crearon temas ni se reenvió ningún mensaje en Telegram.")
            logger.info("Revisa 'PROPUESTA_SERIES_TV.md' y 'propuesta_series_tv.json' para seleccionar las series.")
            return

        # FASE 2: Sincronización
        # Si se pasa --series "Nombre 1, Nombre 2"
        whitelist = None
        for arg in sys.argv:
            if arg.startswith("--series="):
                whitelist = [s.strip() for s in arg.split("=", 1)[1].split(",")]

        await sincronizar_telegram(client, series_dict, series_whitelist=whitelist)


if __name__ == "__main__":
    asyncio.run(main())
