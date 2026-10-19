import asyncio
import os
import re
import unicodedata
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetForumTopicsRequest
from telethon.tl.types import InputMessagesFilterDocument, InputMessagesFilterVideo

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")

BUNKER_SERIES = -1002097175258
PROD_SERIES = -1004331019870

TARGET_SERIES = [
    {"id": "the_wire", "names": ["The Wire", "Bajo escucha"], "years": "2002-2008"},
    {"id": "breaking_bad", "names": ["Breaking Bad"], "years": "2008-2013"},
    {"id": "better_call_saul", "names": ["Better Call Saul"], "years": "2015-2022"},
    {"id": "mad_men", "names": ["Mad Men"], "years": "2007-2015"},
    {"id": "succession", "names": ["Succession"], "years": "2018-2023"},
    {"id": "the_sopranos", "names": ["The Sopranos", "Los Soprano"], "years": "1999-2007"},
    {"id": "peaky_blinders", "names": ["Peaky Blinders"], "years": "2013-2022"},
    {"id": "fargo", "names": ["Fargo"], "years": "2014-"},
    {"id": "mindhunter", "names": ["Mindhunter"], "years": "2017-2019"},
    {"id": "the_americans", "names": ["The Americans"], "years": "2013-2018"},
    {"id": "severance", "names": ["Severance", "Separacion"], "years": "2022-"},
    {"id": "dark", "names": ["Dark"], "years": "2017-2020"},
    {"id": "black_mirror", "names": ["Black Mirror"], "years": "2011-"},
    {"id": "game_of_thrones", "names": ["Game of Thrones", "Juego de Tronos"], "years": "2011-2019"},
    {"id": "the_leftovers", "names": ["The Leftovers"], "years": "2014-2017"},
    {"id": "stranger_things", "names": ["Stranger Things"], "years": "2016-"},
    {"id": "arcane", "names": ["Arcane"], "years": "2021-"},
    {"id": "andor", "names": ["Andor"], "years": "2022-"},
    {"id": "lost", "names": ["Lost", "Perdidos"], "years": "2004-2010"},
    {"id": "chernobyl", "names": ["Chernobyl"], "years": "2019"},
    {"id": "band_of_brothers", "names": ["Band of Brothers", "Hermanos de Sangre"], "years": "2001"},
    {"id": "true_detective", "names": ["True Detective"], "years": "2014-"},
    {"id": "shogun", "names": ["Shōgun", "Shogun"], "years": "2024"},
    {"id": "queens_gambit", "names": ["Gambito de Dama", "The Queen's Gambit"], "years": "2020"},
    {"id": "fleabag", "names": ["Fleabag"], "years": "2016-2019"},
    {"id": "the_bear", "names": ["The Bear"], "years": "2022-"},
    {"id": "the_office", "names": ["The Office", "The Office US"], "years": "2005-2013"},
    {"id": "bojack_horseman", "names": ["BoJack Horseman", "Bojack Horseman"], "years": "2014-2020"},
    {"id": "atlanta", "names": ["Atlanta"], "years": "2016-2022"},
    {"id": "the_white_lotus", "names": ["The White Lotus", "White Lotus"], "years": "2021-"},
]

def normalize(s: str) -> str:
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode('utf-8')
    s = re.sub(r'[^a-z0-9\s]', ' ', s.lower())
    return re.sub(r'\s+', ' ', s).strip()

def is_title_match(names, raw_title):
    norm_title = normalize(raw_title)
    # Palabras a evitar si el nombre es corto
    disallowed_short = {
        "dark": ["matter", "winds", "angel", "skies", "shadows", "knight", "crystal"],
        "lost": ["space", "girl", "room", "canvas", "in", "tapes"],
        "arcane": ["league"],
        "the bear": ["bear in the big blue house", "grizzly"],
        "fargo": [],
        "atlanta": [],
        "the americans": ["crime", "horror", "pie", "gods", "dad"],
        "the office": ["uk", "australia", "india", "chile", "france"]
    }

    for name in names:
        norm_name = normalize(name)
        if not norm_name:
            continue

        # Match exacto
        if norm_title == norm_name:
            return True

        # Chequear descalificaciones para nombres cortos
        if norm_name in disallowed_short:
            disqualified = False
            for dis in disallowed_short[norm_name]:
                if dis in norm_title:
                    disqualified = True
                    break
            if disqualified:
                continue

        # Comprobar límite de palabra
        pattern = r'(?:^|\b)' + re.escape(norm_name) + r'(?:\b|$)'
        if re.search(pattern, norm_title):
            # Si el nombre es de 1 sola palabra corta (<= 5 caracteres), asegurarnos de que lo que sigue es año, temporada o calidad
            if len(norm_name.split()) == 1 and len(norm_name) <= 6:
                rem = norm_title.replace(norm_name, '').strip()
                if not rem:
                    return True
                # Si lo restante contiene dígitos (año o t01), o temporada/completa, o resolución
                if re.search(r'\b(19\d\d|20\d\d|t\d+|s\d+|temporada|completa|1080p|720p|2160p|4k|hdtv|web)\b', rem):
                    return True
                # Si no, podría ser otra cosa
                continue
            return True

    return False

async def get_all_topics(client, entity):
    topics = []
    offset_date = None
    offset_id = 0
    offset_topic = 0
    while True:
        try:
            res = await client(GetForumTopicsRequest(
                peer=entity,
                offset_date=offset_date,
                offset_id=offset_id,
                offset_topic=offset_topic,
                limit=100
            ))
            if not res.topics:
                break
            topics.extend(res.topics)
            if len(res.topics) < 100:
                break
            last_t = res.topics[-1]
            offset_date = res.messages[-1].date if res.messages else None
            offset_id = res.messages[-1].id if res.messages else 0
            offset_topic = last_t.id
        except Exception as e:
            print(f"Error obteniendo topics: {e}")
            break
    return topics

async def count_files_in_topic(client, entity, topic_id):
    count = 0
    mkv_count = 0
    mp4_count = 0
    other_count = 0
    samples = []
    try:
        async for m in client.iter_messages(entity, reply_to=topic_id, limit=600):
            if m.id == topic_id:
                continue
            if m.file:
                count += 1
                fname = (getattr(m.file, 'name', '') or '').lower()
                if fname.endswith('.mkv'):
                    mkv_count += 1
                elif fname.endswith('.mp4'):
                    mp4_count += 1
                else:
                    other_count += 1
                if len(samples) < 3 and fname:
                    samples.append(fname)
    except Exception as e:
        print(f"Error contando archivos en topic {topic_id}: {e}")
    return count, mkv_count, mp4_count, other_count, samples

async def main():
    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client:
        me = await client.get_me()
        print(f"🔍 Conectado como: {me.first_name} (ID: {me.id})")
        
        # 1. Obtener diálogos accesibles
        print("\n📡 Inspeccionando diálogos accesibles...")
        dialogs = await client.get_dialogs(limit=150)
        accessible_chats = {}
        for d in dialogs:
            title_norm = normalize(d.title)
            accessible_chats[d.id] = d
            if any(k in title_norm for k in ["castellana", "series", "comunidad", "bunker", "flipe"]):
                print(f"   Chat encontrado: '{d.title}' (ID: {d.id}, es foro: {getattr(d.entity, 'forum', False)})")

        # 2. Catálogo de Búnker Series TV
        print(f"\n📡 Analizando Búnker 'SERIES TV' ({BUNKER_SERIES})...")
        bunker_ent = await client.get_entity(BUNKER_SERIES)
        bunker_topics = await get_all_topics(client, bunker_ent)
        print(f"Total temas en Búnker: {len(bunker_topics)}")

        # 3. Comprobar cada una de las 30 series en el Búnker
        results = []
        missing_series = []

        for item in TARGET_SERIES:
            serie_name_main = item["names"][0]
            matched_topic = None
            for t in bunker_topics:
                if is_title_match(item["names"], t.title):
                    matched_topic = t
                    break

            if matched_topic:
                c, mkv, mp4, other, samples = await count_files_in_topic(client, bunker_ent, matched_topic.id)
                results.append({
                    "name": serie_name_main,
                    "year": item["years"],
                    "status": "DISPONIBLE_BUNKER",
                    "bunker_topic_id": matched_topic.id,
                    "bunker_topic_title": matched_topic.title,
                    "files_total": c,
                    "mkv": mkv,
                    "mp4": mp4,
                    "other": other,
                    "samples": samples
                })
            else:
                missing_series.append(item)
                results.append({
                    "name": serie_name_main,
                    "year": item["years"],
                    "status": "NO_EN_BUNKER",
                    "bunker_topic_id": None,
                    "bunker_topic_title": None,
                    "files_total": 0,
                    "mkv": 0,
                    "mp4": 0,
                    "other": 0,
                    "samples": []
                })

        print(f"\n📊 Series encontradas en Búnker: {len(results) - len(missing_series)} / 30")
        print(f"📊 Series no encontradas en Búnker: {len(missing_series)} / 30")

        # 4. Para las no encontradas en Búnker, buscar en los canales de Comunidad Castellana
        comm_candidates = []
        for cid, d in accessible_chats.items():
            if cid in [BUNKER_SERIES, PROD_SERIES]:
                continue
            t_norm = normalize(d.title)
            if "castellana" in t_norm or "comunidad" in t_norm or "series" in t_norm:
                comm_candidates.append(d)

        print(f"\n📡 Buscando en {len(comm_candidates)} canales comunitarios disponibles...")
        for cchat in comm_candidates:
            print(f"\n   -> Explorando: '{cchat.title}' (ID: {cchat.id})")
            is_forum = getattr(cchat.entity, 'forum', False)
            c_topics = []
            if is_forum:
                c_topics = await get_all_topics(client, cchat.entity)
                print(f"      Total temas en '{cchat.title}': {len(c_topics)}")

            for m_item in missing_series:
                m_res = next(r for r in results if r["name"] == m_item["names"][0])
                if m_res.get("found_in_community"):
                    continue

                # 4.1 Buscar por temas del foro si es foro
                if is_forum and c_topics:
                    for ct in c_topics:
                        if is_title_match(m_item["names"], ct.title):
                            fc, mkv, mp4, oth, sam = await count_files_in_topic(client, cchat.entity, ct.id)
                            if fc > 0 and (mkv > 0 or mp4 > 0):
                                m_res["found_in_community"] = True
                                m_res["comm_chat_id"] = cchat.id
                                m_res["comm_chat_title"] = cchat.title
                                m_res["comm_topic_id"] = ct.id
                                m_res["comm_topic_title"] = ct.title
                                m_res["comm_files"] = fc
                                m_res["comm_mkv"] = mkv
                                m_res["comm_mp4"] = mp4
                                m_res["comm_samples"] = sam
                                print(f"      🎯 [TEMA] '{m_item['names'][0]}' en '{ct.title}' ({fc} archivos: {mkv} mkv, {mp4} mp4)")
                                break

                # 4.2 Si no se encontró por tema, buscar mensajes de vídeo/archivo en el chat
                if not m_res.get("found_in_community"):
                    for name in m_item["names"]:
                        try:
                            search_msgs = await client.get_messages(cchat.entity, search=name, limit=30)
                            valid_files = [m for m in search_msgs if m.file and (m.file.name or '').lower().endswith(('.mkv', '.mp4'))]
                            if valid_files:
                                m_res["found_in_community"] = True
                                m_res["comm_chat_id"] = cchat.id
                                m_res["comm_chat_title"] = cchat.title
                                top_id = getattr(valid_files[0].reply_to, 'reply_to_top_id', None) or getattr(valid_files[0].reply_to, 'reply_to_msg_id', None)
                                m_res["comm_topic_id"] = top_id
                                m_res["comm_topic_title"] = f"Búsqueda mensaje ({len(valid_files)}+ caps)"
                                m_res["comm_files"] = len(valid_files)
                                m_res["comm_mkv"] = sum(1 for vf in valid_files if (vf.file.name or '').lower().endswith('.mkv'))
                                m_res["comm_mp4"] = sum(1 for vf in valid_files if (vf.file.name or '').lower().endswith('.mp4'))
                                m_res["comm_samples"] = [vf.file.name for vf in valid_files[:3] if vf.file and vf.file.name]
                                print(f"      🎯 [BÚSQUEDA] '{m_item['names'][0]}' en '{cchat.title}' ({len(valid_files)} archivos encontrados)")
                                break
                        except Exception as e:
                            pass

        # 5. Generar informe formateado en consola
        print("\n" + "="*85)
        print("INFORME DE AUDITORÍA: 30 SERIES IMPRESCINDIBLES DEL SIGLO XXI")
        print("="*85)
        for idx, r in enumerate(results, 1):
            if r["status"] == "DISPONIBLE_BUNKER":
                fmt = f"MKV: {r['mkv']}, MP4: {r['mp4']}"
                if r['other'] > 0:
                    fmt += f", Otros: {r['other']}"
                print(f"{idx:2d}. [EN BÚNKER] {r['name']} ({r['year']})")
                print(f"    Tema Búnker: \"{r['bunker_topic_title']}\" (ID: {r['bunker_topic_id']})")
                print(f"    Capítulos: {r['files_total']} ({fmt})")
                if r['samples']:
                    print(f"    Muestra: {r['samples'][:2]}")
            elif r.get("found_in_community"):
                fmt = f"MKV: {r['comm_mkv']}, MP4: {r['comm_mp4']}"
                print(f"{idx:2d}. [DISPONIBLE EN COMUNIDAD] {r['name']} ({r['year']})")
                print(f"    Canal: \"{r['comm_chat_title']}\" | Tema: \"{r['comm_topic_title']}\" (ID: {r['comm_topic_id']})")
                print(f"    Capítulos localizados: {r['comm_files']} ({fmt})")
                if r['comm_samples']:
                    print(f"    Muestra: {r['comm_samples'][:2]}")
            else:
                print(f"{idx:2d}. [NO LOCALIZADA] {r['name']} ({r['year']})")
                print(f"    No se encontró en Búnker ni en Comunidad Castellana actual.")

        print("="*85)

if __name__ == "__main__":
    asyncio.run(main())
