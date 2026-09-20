#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
filtrar_y_dividir_series.py
Depuración, filtrado de calidad y clasificación temática automática del catálogo de Series TV
utilizando metadatos canónicos de la API de TMDb.

Genera 4 archivos JSON temáticos y un reporte resumen:
1. series_espanolas.json
2. series_turcas_y_telenovelas.json
3. series_retro_clasicas.json
4. series_internacionales.json
5. resumen_depurado.txt
"""

import os
import sys
import re
import json
import time
import socket
import logging
import threading
import urllib.parse
import urllib.request
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

# Asegurar timeout global en sockets para evitar bloqueos por DNS o SSL
socket.setdefaulttimeout(7.0)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("DataEngineerSeries")

# Configuración y Constantes
INPUT_JSON = "propuesta_series_tv.json"
TMDB_CACHE_FILE = "tmdb_metadata_cache.json"
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "2b7cd7b237fe99884613b230a910a09c")

OUT_ESPANOLAS = "series_espanolas.json"
OUT_TURCAS_NOVELAS = "series_turcas_y_telenovelas.json"
OUT_RETRO = "series_retro_clasicas.json"
OUT_INTERNACIONALES = "series_internacionales.json"
OUT_RESUMEN = "resumen_depurado.txt"

# Países considerados en la categoría de telenovelas / producciones hispanas-latinas
LATAM_COUNTRIES = {
    "MX", "CO", "AR", "VE", "CL", "PE", "BR", "UY", "CU", "DO", "PR", "GT", "EC", "PY", "BO", "CR", "PA"
}

GENRE_SOAP_ID = 10766

GENRE_NAMES = {
    10759: "Action & Adventure",
    16: "Animación",
    35: "Comedia",
    80: "Crimen",
    99: "Documental",
    18: "Drama",
    10751: "Familia",
    10762: "Kids",
    9648: "Misterio",
    10763: "News",
    10764: "Reality",
    10765: "Sci-Fi & Fantasy",
    10766: "Soap",
    10767: "Talk",
    10768: "War & Politics",
    37: "Western"
}


# -----------------------------------------------------------------------------
# 1. Filtro de Calidad y Detección de Ruido
# -----------------------------------------------------------------------------
def is_junk_title(name: str) -> bool:
    """Detecta nombres genéricos, residuales o sin limpiar."""
    clean = name.strip()
    if len(clean) < 3:
        return True
    if clean.isdigit():
        return True

    lower = clean.lower()

    # Códigos de capítulo o etiquetas técnicas residuales
    if re.match(r"^(?:cap[íi]tulo|cap|ep|temporada|temp|s\d+|t\d+|\d{1,2}x\d{1,3})\b", lower):
        return True

    technical_prefixes = (
        "1080p", "720p", "4k", "2160p", "hdtv", "web-dl", "webrip", "bluray",
        "bdrip", "dvdrip", "x264", "x265", "hevc", "microhd", "remux"
    )
    if any(lower.startswith(prefix) for prefix in technical_prefixes):
        return True

    junk_indicators = [
        "uploaded by", "compartir.mkv", "locosxelcine", "cinepalomitas",
        "castellano", "español", "latino", "subtitulado", "dual", "multi"
    ]
    noise_count = sum(1 for ind in junk_indicators if ind in lower)
    if noise_count >= 2:
        return True

    return False


def clean_query_title(name: str) -> str:
    """Limpia el título para mejorar la búsqueda en la API de TMDb."""
    t = name.strip()
    t = re.sub(r"\s*\(\d{4}\)$", "", t)
    t = re.sub(r"[-–—._\s]+$", "", t)
    return t.strip()


# -----------------------------------------------------------------------------
# 2. Cliente y Caché de TMDb para Metadatos (Thread-Safe)
# -----------------------------------------------------------------------------
class TmdbMetadataClient:
    def __init__(self, api_key: str, cache_file: str = TMDB_CACHE_FILE):
        self.api_key = api_key
        self.cache_file = cache_file
        self.cache: Dict[str, Optional[Dict[str, Any]]] = {}
        self.lock = threading.Lock()
        self._load_cache()

    def _load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
                logger.info(f"Caché de metadatos TMDb cargado con {len(self.cache)} entradas.")
            except Exception as e:
                logger.warning(f"Error cargando {self.cache_file}: {e}")

    def save_cache(self):
        with self.lock:
            snapshot = dict(self.cache)
        tmp_file = self.cache_file + ".tmp"
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2, ensure_ascii=False)
            os.replace(tmp_file, self.cache_file)
        except Exception as e:
            logger.warning(f"Error guardando caché: {e}")

    def get_cached(self, norm_key: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        with self.lock:
            if norm_key in self.cache:
                return True, self.cache[norm_key]
        return False, None

    def set_cached(self, norm_key: str, value: Optional[Dict[str, Any]]):
        with self.lock:
            self.cache[norm_key] = value

    def fetch_show_metadata(self, title: str, local_ep_count: int) -> Optional[Dict[str, Any]]:
        norm_key = title.strip().lower()
        cached, val = self.get_cached(norm_key)
        if cached:
            return val

        query = clean_query_title(title)
        if len(query) < 2:
            self.set_cached(norm_key, None)
            return None

        time.sleep(0.03)

        for attempt in range(2):
            try:
                encoded_query = urllib.parse.quote(query)
                url = f"https://api.themoviedb.org/3/search/tv?api_key={self.api_key}&query={encoded_query}&language=es-ES"
                req = urllib.request.Request(url, headers={"User-Agent": "TeveFlipeSync/2.0"})

                with urllib.request.urlopen(req, timeout=6) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    results = data.get("results", [])

                    if not results:
                        self.set_cached(norm_key, None)
                        return None

                    best = results[0]
                    tmdb_id = best.get("id")
                    official_title = best.get("name") or best.get("original_name")
                    origin_country = best.get("origin_country") or []
                    orig_lang = best.get("original_language") or ""
                    first_air_date = best.get("first_air_date") or ""
                    genre_ids = best.get("genre_ids") or []

                    meta = {
                        "tmdb_id": tmdb_id,
                        "titulo_oficial": official_title.strip() if official_title else title,
                        "original_name": best.get("original_name", ""),
                        "origin_country": origin_country,
                        "original_language": orig_lang,
                        "first_air_date": first_air_date,
                        "genre_ids": genre_ids,
                        "genres": [GENRE_NAMES.get(gid, "Otro") for gid in genre_ids],
                        "type": "Standard",
                        "number_of_episodes": 0
                    }

                    # Si tiene menos de 3 episodios detectados, consultar detalles para verificar si es miniserie
                    if local_ep_count < 3 and tmdb_id:
                        try:
                            time.sleep(0.02)
                            detail_url = f"https://api.themoviedb.org/3/tv/{tmdb_id}?api_key={self.api_key}&language=es-ES"
                            detail_req = urllib.request.Request(detail_url, headers={"User-Agent": "TeveFlipeSync/2.0"})
                            with urllib.request.urlopen(detail_req, timeout=5) as dresp:
                                detail_data = json.loads(dresp.read().decode("utf-8"))
                                meta["type"] = detail_data.get("type", "Standard")
                                meta["number_of_episodes"] = detail_data.get("number_of_episodes", 0)
                        except Exception:
                            pass

                    self.set_cached(norm_key, meta)
                    return meta

            except Exception as e:
                if attempt == 0:
                    time.sleep(1.0)
                else:
                    self.set_cached(norm_key, None)
                    return None

        return None


# -----------------------------------------------------------------------------
# 3. Lógica de Clasificación Temática
# -----------------------------------------------------------------------------
def classify_series(meta: Dict[str, Any]) -> str:
    """
    Clasifica una serie en una de las 4 categorías temáticas:
    1. 'espanolas'
    2. 'turcas_y_telenovelas'
    3. 'retro_clasicas'
    4. 'internacionales'
    """
    origin_country = meta.get("origin_country", [])
    orig_lang = meta.get("original_language", "").lower()
    genre_ids = meta.get("genre_ids", [])
    first_air_date = meta.get("first_air_date", "")

    # 1. Series Españolas
    if "ES" in origin_country or (orig_lang == "es" and "ES" in origin_country):
        return "espanolas"

    # 2. Series Turcas y Telenovelas
    if "TR" in origin_country:
        return "turcas_y_telenovelas"
    if GENRE_SOAP_ID in genre_ids:
        return "turcas_y_telenovelas"
    if any(c in LATAM_COUNTRIES for c in origin_country):
        return "turcas_y_telenovelas"

    # 3. Series Retro / Clásicas (Primer episodio anterior a 2010)
    year = None
    if first_air_date and len(first_air_date) >= 4:
        try:
            year = int(first_air_date[:4])
        except ValueError:
            year = None

    if year is not None and year < 2010:
        return "retro_clasicas"

    # 4. Series Internacionales (Estrenadas de 2010 en adelante)
    return "internacionales"


# -----------------------------------------------------------------------------
# 4. Proceso Principal de Ingeniería de Datos
# -----------------------------------------------------------------------------
def procesar_catalogo():
    logger.info("=" * 65)
    logger.info("🚀 INICIANDO DEPURACIÓN Y CLASIFICACIÓN TEMÁTICA DE SERIES TV")
    logger.info("=" * 65)

    if not os.path.exists(INPUT_JSON):
        logger.error(f"❌ Archivo fuente no encontrado: {INPUT_JSON}")
        return

    logger.info(f"Cargando catálogo fuente '{INPUT_JSON}'...")
    with open(INPUT_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    series_raw: Dict[str, Any] = data.get("series", {})
    total_original = len(series_raw)
    logger.info(f"Total títulos originales en catálogo: {total_original}")

    tmdb_client = TmdbMetadataClient(api_key=TMDB_API_KEY)

    # 1. Pre-filtrado local de ruido obvio y selección de candidatos a enriquecer
    logger.info("Aplicando pre-filtro de calidad y ruido...")
    candidatos_para_tmdb: List[Tuple[str, int]] = []
    descartados_ruido = 0
    descartados_pocos_episodios = 0

    for raw_name, info in series_raw.items():
        if is_junk_title(raw_name):
            descartados_ruido += 1
            continue

        ep_count = info.get("total_capitulos", len(info.get("capitulos", [])))

        # Regla: descartar entradas de 1 solo episodio sin indicación de miniserie
        if ep_count == 1:
            lower = raw_name.lower()
            if not any(k in lower for k in ["miniserie", "completa", "temporada completa"]):
                descartados_pocos_episodios += 1
                continue

        candidatos_para_tmdb.append((raw_name, ep_count))

    # Ordenar candidatos: primero las series con más episodios
    candidatos_para_tmdb.sort(key=lambda x: x[1], reverse=True)

    logger.info(f"Descartados por ruido/genéricos: {descartados_ruido}")
    logger.info(f"Descartados por episodio único aislado: {descartados_pocos_episodios}")
    logger.info(f"Candidatos limpios a consultar en TMDb: {len(candidatos_para_tmdb)}")

    # 2. Consultas concurrentes a TMDb
    titulos_a_consultar = [
        (name, ep_c) for name, ep_c in candidatos_para_tmdb
        if name.strip().lower() not in tmdb_client.cache
    ]
    logger.info(f"Títulos pendientes de consultar en TMDb: {len(titulos_a_consultar)} (en caché: {len(candidatos_para_tmdb) - len(titulos_a_consultar)})")

    if titulos_a_consultar:
        completados = 0
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [
                executor.submit(tmdb_client.fetch_show_metadata, name, ep_c)
                for name, ep_c in titulos_a_consultar
            ]
            for f in as_completed(futures):
                try:
                    f.result()
                except Exception as ex:
                    logger.debug(f"Error worker: {ex}")
                completados += 1
                if completados % 500 == 0 or completados == len(titulos_a_consultar):
                    logger.info(f"   TMDb progreso: {completados}/{len(titulos_a_consultar)} completados...")
                    tmdb_client.save_cache()

        tmdb_client.save_cache()

    # 3. Filtrado definitivo y Agrupación Canónica
    logger.info("Consolidando series aprobadas según criterios de calidad...")
    descartados_sin_tmdb = 0
    descartados_no_miniserie = 0

    series_aprobadas: Dict[str, Dict[str, Any]] = {}

    for raw_name, ep_count in candidatos_para_tmdb:
        cached, meta = tmdb_client.get_cached(raw_name.strip().lower())

        if not meta or not meta.get("tmdb_id"):
            descartados_sin_tmdb += 1
            continue

        # Validar regla de menos de 3 episodios:
        # Solo se permite si en TMDb figura como number_of_episodes <= 8 o type == "Miniseries"
        if ep_count < 3:
            is_miniseries = (meta.get("type") == "Miniseries") or (0 < meta.get("number_of_episodes", 0) <= 8)
            if not is_miniseries:
                descartados_no_miniserie += 1
                continue

        canonical_title = meta["titulo_oficial"].strip()
        raw_info = series_raw[raw_name]

        if canonical_title not in series_aprobadas:
            series_aprobadas[canonical_title] = {
                "tmdb_id": meta["tmdb_id"],
                "titulo_oficial": canonical_title,
                "original_name": meta.get("original_name", ""),
                "origin_country": meta.get("origin_country", []),
                "original_language": meta.get("original_language", ""),
                "first_air_date": meta.get("first_air_date", ""),
                "genres": meta.get("genres", []),
                "type": meta.get("type", "Standard"),
                "categoria_destino": classify_series(meta),
                "total_capitulos": 0,
                "temporadas": set(),
                "capitulos": []
            }

        # Consolidar episodios y temporadas (evitando duplicar id de mensaje)
        entry = series_aprobadas[canonical_title]
        existing_ids = set(c["message_id"] for c in entry["capitulos"])
        for cap in raw_info.get("capitulos", []):
            if cap["message_id"] not in existing_ids:
                entry["capitulos"].append(cap)
                entry["temporadas"].add(cap.get("season", 1))
                existing_ids.add(cap["message_id"])

    # Finalizar conteos de cada serie aprobada
    for entry in series_aprobadas.values():
        entry["temporadas"] = sorted(list(entry["temporadas"]))
        entry["capitulos"].sort(key=lambda x: (x.get("season", 1), x.get("episode", 1), x.get("message_id", 0)))
        entry["total_capitulos"] = len(entry["capitulos"])

    logger.info(f"Total series reales aprobadas tras filtro: {len(series_aprobadas)}")
    logger.info(f"Descartados sin coincidencia TMDb: {descartados_sin_tmdb}")
    logger.info(f"Descartados <3 eps que no eran miniseries: {descartados_no_miniserie}")

    # 4. Dividir en los 4 archivos temáticos
    grupos: Dict[str, Dict[str, Any]] = {
        "espanolas": {},
        "turcas_y_telenovelas": {},
        "retro_clasicas": {},
        "internacionales": {}
    }

    for title, sdata in sorted(series_aprobadas.items(), key=lambda x: x[1]["total_capitulos"], reverse=True):
        cat = sdata["categoria_destino"]
        grupos[cat][title] = sdata

    # Guardar los 4 archivos JSON
    archivos_salida = {
        "espanolas": OUT_ESPANOLAS,
        "turcas_y_telenovelas": OUT_TURCAS_NOVELAS,
        "retro_clasicas": OUT_RETRO,
        "internacionales": OUT_INTERNACIONALES
    }

    for cat_key, file_name in archivos_salida.items():
        data_to_write = {
            "categoria": cat_key,
            "total_series": len(grupos[cat_key]),
            "total_capitulos": sum(s["total_capitulos"] for s in grupos[cat_key].values()),
            "series": grupos[cat_key]
        }
        with open(file_name, "w", encoding="utf-8") as f:
            json.dump(data_to_write, f, indent=2, ensure_ascii=False)
        logger.info(f"💾 Guardado '{file_name}': {len(grupos[cat_key])} series ({data_to_write['total_capitulos']} caps).")

    # 5. Generar reporte resumen_depurado.txt
    generar_reporte_resumen(total_original, series_aprobadas, grupos)
    logger.info(f"📄 Reporte generado en '{OUT_RESUMEN}'.")
    logger.info("🎉 Proceso de ingeniería de datos completado con éxito.")


def generar_reporte_resumen(
    total_original: int,
    series_aprobadas: Dict[str, Any],
    grupos: Dict[str, Dict[str, Any]]
):
    total_reales = len(series_aprobadas)
    total_caps_reales = sum(s["total_capitulos"] for s in series_aprobadas.values())

    lineas = []
    lineas.append("=" * 80)
    lineas.append("📊 REPORTE DE DEPURACIÓN Y CLASIFICACIÓN TEMÁTICA DE SERIES TV")
    lineas.append(f"Fecha de generación: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lineas.append("=" * 80)
    lineas.append("")
    lineas.append("1. MÉTRICAS GENERALES")
    lineas.append("-" * 40)
    lineas.append(f"• Total títulos brutos iniciales: {total_original:,}")
    lineas.append(f"• Total series canónicas aprobadas tras filtros: {total_reales:,}")
    lineas.append(f"• Total archivos de vídeo incluidos en series: {total_caps_reales:,}")
    lineas.append(f"• Tasa de reducción de ruido: {((total_original - total_reales) / total_original) * 100:.2f}%")
    lineas.append("")
    lineas.append("2. DISTRIBUCIÓN POR CATEGORÍA TEMÁTICA")
    lineas.append("-" * 40)

    nombres_legibles = {
        "espanolas": "🇪🇸 Series Españolas (series_espanolas.json)",
        "turcas_y_telenovelas": "🇹🇷 Series Turcas y Telenovelas (series_turcas_y_telenovelas.json)",
        "retro_clasicas": "📼 Series Retro / Clásicas (<2010) (series_retro_clasicas.json)",
        "internacionales": "🌍 Series Internacionales Modernas (>=2010) (series_internacionales.json)"
    }

    for cat_key in ["espanolas", "turcas_y_telenovelas", "retro_clasicas", "internacionales"]:
        sub_series = grupos[cat_key]
        sub_caps = sum(s["total_capitulos"] for s in sub_series.values())
        lineas.append(f"• {nombres_legibles[cat_key]}")
        lineas.append(f"   -> Series: {len(sub_series):,} | Capítulos: {sub_caps:,}")

    lineas.append("")
    lineas.append("=" * 80)
    lineas.append("3. LISTADOS DETALLADOS DE CADA CATEGORÍA")
    lineas.append("=" * 80)

    for cat_key in ["espanolas", "turcas_y_telenovelas", "retro_clasicas", "internacionales"]:
        sub_series = grupos[cat_key]
        lineas.append("")
        lineas.append("#" * 80)
        lineas.append(f"CATÁLOGO: {nombres_legibles[cat_key].upper()} ({len(sub_series)} series)")
        lineas.append("#" * 80)
        lineas.append(f"{'#':<5} {'SERIE':<50} {'CAPS':<8} {'TEMPS':<15} {'AÑO'}")
        lineas.append("-" * 85)

        for i, (titulo, sdata) in enumerate(sub_series.items(), 1):
            temps_str = "T" + ",".join(str(t) for t in sdata.get("temporadas", []))
            if len(temps_str) > 14:
                temps_str = temps_str[:11] + "..."
            year = sdata.get("first_air_date", "")[:4] or "N/A"
            lineas.append(f"{i:<5} {titulo[:48]:<50} {sdata['total_capitulos']:<8} {temps_str:<15} {year}")

    with open(OUT_RESUMEN, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")


if __name__ == "__main__":
    procesar_catalogo()
