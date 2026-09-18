import json
import os
import re
import sys
from collections import defaultdict

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

with open("analisis_anime.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# Cargamos el reporte de películas confirmadas para EXCLUIR cualquier mensaje que sea película
pelis_ids = set()
if os.path.exists("criba_peliculas_reporte.json"):
    try:
        with open("criba_peliculas_reporte.json", "r", encoding="utf-8") as f:
            cr = json.load(f)
            pelis_ids = {p["message_id"] for p in cr.get("peliculas", [])}
    except Exception:
        pass

print(f"Total películas excluidas para no mezclar en series: {len(pelis_ids)}")

# Patrones para limpiar títulos de temporadas y dejar solo el nombre de la serie
SEASON_PATTERNS = [
    r"(?i)\s*[-_.]?\s*(?:temporada|temp|season|t)\s*[-_.]?\s*\d{1,2}\b.*$",
    r"(?i)\s*[-_.]?\s*\d{1,2}(?:st|nd|rd|th)?\s*season\b.*$",
    r"(?i)\s*[-_.]?\s*s\d{1,2}\b.*$",
    r"(?i)\s*[-_.]?\s*parte\s*\d{1,2}\b.*$",
    r"(?i)\s*[-_.]?\s*\d{1,2}x\d{1,3}\b.*$",
    r"(?i)\s*[-_.]?\s*cap[ií]tulo.*$",
    r"(?i)\s*[-_.]?\s*episodio.*$",
]

def normalizar_nombre_serie(raw_title: str, filename: str = "") -> str:
    t = raw_title.strip()

    # Quitar extensiones
    t = re.sub(r"\.(mkv|mp4|avi|mov|webm)$", "", t, flags=re.IGNORECASE).strip()

    # Quitar tags tipo [1080p], (Castellano), [Dual], etc.
    t = re.sub(r"\[[^\]]*\]|\([^\)]*\)", " ", t).strip()

    # Quitar prefijos numéricos de orden (01, 001, etc.)
    t = re.sub(r"^\d{1,3}\s*[-_.]?\s*", "", t).strip()

    # Quitar menciones de temporada / season / partes
    for pat in SEASON_PATTERNS:
        t = re.sub(pat, "", t).strip()

    # Limpiar signos y espacios
    t = re.sub(r"[-_.]+", " ", t).strip()
    t = re.sub(r"\s{2,}", " ", t).strip()

    return t.title()

# Agrupar las series
series_dict = defaultdict(lambda: {
    "episodes": [],
    "seasons": set(),
    "msg_ids": set(),
    "sample_files": []
})

for s_key, s_data in data["series"].items():
    raw_title = s_data["title"]
    # Si empieza con 01X o similar, no tiene nombre limpio
    if raw_title.startswith("01X") or raw_title.startswith("00X"):
        continue

    norm_title = normalizar_nombre_serie(raw_title)
    if len(norm_title) < 3:
        continue

    entry = series_dict[norm_title]
    entry["seasons"].update(s_data.get("seasons", []))
    for sf in s_data.get("sample_files", []):
        if sf not in entry["sample_files"]:
            entry["sample_files"].append(sf)

    # Si hay episodios y msg_range
    mr = s_data.get("msg_range", "")
    entry["episodes"].append({
        "raw_title": raw_title,
        "count": s_data.get("total_episodes", 0),
        "msg_range": mr,
        "size_gb": s_data.get("total_size_gb", 0)
    })

# Consolidar métricas
series_consolidadas = []
for title, item in series_dict.items():
    total_caps = sum(e["count"] for e in item["episodes"])
    total_gb = round(sum(e["size_gb"] for e in item["episodes"]), 2)
    seasons_sorted = sorted(list(item["seasons"])) if item["seasons"] else [1]

    # Regla estricta: Mínimo 3 episodios para considerarse serie
    if total_caps >= 3:
        series_consolidadas.append({
            "title": title,
            "total_episodes": total_caps,
            "seasons": seasons_sorted,
            "total_gb": total_gb,
            "sub_bloques": len(item["episodes"]),
            "ranges": [e["msg_range"] for e in item["episodes"] if e.get("msg_range")],
            "sample_files": item["sample_files"][:3]
        })

# Ordenar por cantidad de episodios (de mayor a menor)
series_consolidadas.sort(key=lambda x: x["total_episodes"], reverse=True)

print(f"Total Series Consolidadas Limpias (>= 3 capítulos): {len(series_consolidadas)}")
print(f"Total Episodios agrupados: {sum(s['total_episodes'] for s in series_consolidadas)}")

# Guardar en JSON maestro
with open("catalogo_maestro_series_anime.json", "w", encoding="utf-8") as f:
    json.dump(series_consolidadas, f, indent=2, ensure_ascii=False)

# Generar Markdown
md = []
md.append("# ⛩️ Catálogo Maestro Consolidado de Series Anime")
md.append(f"\nTotal de Series Verificadas (1 Tema por Serie, sin capítulos sueltos ni temas por temporada): **{len(series_consolidadas)} series**.")
md.append(f"Total de Episodios: **{sum(s['total_episodes'] for s in series_consolidadas)} episodios**.\n")
md.append("| # | Título del Tema (Serie Única) | Temporadas Incluidas | Total Episodios | Tamaño Total | Muestra de Archivos |")
md.append("|---|------------------------------|:--------------------:|:---------------:|:------------:|---------------------|")

for idx, s in enumerate(series_consolidadas, 1):
    seasons_str = f"T{', T'.join(map(str, s['seasons']))}" if s['seasons'] else "T1"
    sample_str = "<br>".join(f"`{sf}`" for sf in s['sample_files'])
    md.append(f"| {idx} | **{s['title']}** | {seasons_str} | **{s['total_episodes']} caps** | {s['total_gb']} GB | {sample_str} |")

with open("PROPUESTA_SERIES_ANIME.md", "w", encoding="utf-8") as f:
    f.write("\n".join(md))

print("Archivos 'catalogo_maestro_series_anime.json' y 'PROPUESTA_SERIES_ANIME.md' generados exitosamente.")
