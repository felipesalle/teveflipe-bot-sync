import asyncio
import os
import re
import unicodedata
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetForumTopicsRequest

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")
TELEGRAM_STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION", "")

BUNKER_SERIES = -1002097175258
PROD_SERIES = -1004331019870
COMMUNITY_SERIES_CHAT = -1002257262928

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
    
    disallowed_map = {
        "the wire": ["wire in the blood"],
        "dark": ["matter", "winds", "angel", "skies", "shadows", "knight", "crystal", "justice", "runner", "water"],
        "lost": ["space", "girl", "room", "canvas", "in the", "in space", "tapes", "dawson", "das perdidos", "ninos perdidos"],
        "arcane": ["league"],
        "the bear": ["masha", "grizzly", "bear in the big"],
        "fargo": [],
        "atlanta": [],
        "the americans": ["greatest", "horror", "pie", "gods", "dad", "crime"],
        "the office": ["uk", "australia", "india", "chile", "france"],
        "separacion": ["cinco grados", "dorama", "amor de verdad", "h2o", "cinco hermanos", "ansiedad"],
        "severance": ["h2o", "cinco hermanos"],
        "gambito de dama": ["reglas del juego"],
        "hermanos de sangre": ["s04", "sangre de mi"],
    }

    for name in names:
        norm_name = normalize(name)
        if not norm_name:
            continue

        if norm_title == norm_name:
            return True

        if norm_name in disallowed_map:
            if any(dis in norm_title for dis in disallowed_map[norm_name]):
                continue

        pattern = r'(?:^|\b)' + re.escape(norm_name) + r'(?:\b|$)'
        if re.search(pattern, norm_title):
            if len(norm_name.split()) == 1 and len(norm_name) <= 6:
                rem = norm_title.replace(norm_name, '').strip()
                if not rem:
                    return True
                if re.search(r'\b(19\d\d|20\d\d|t\d+|s\d+|temporada|completa|1080p|720p|2160p|4k|hdtv|web)\b', rem):
                    return True
                continue
            return True

    return False

async def get_all_topics(client, entity):
    all_topics = []
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
        except Exception as e:
            print(f"Error recuperando temas: {e}")
            break
    return all_topics

async def count_files_in_topic(client, entity, topic_id):
    count = 0
    mkv_count = 0
    mp4_count = 0
    other_count = 0
    samples = []
    try:
        async for m in client.iter_messages(entity, reply_to=topic_id, limit=500):
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

async def search_files(client, chat_entity, names, topic_id=None):
    valid_files = []
    for name in names:
        try:
            kwargs = {"search": name, "limit": 60}
            if topic_id:
                kwargs["reply_to"] = topic_id
            async for m in client.iter_messages(chat_entity, **kwargs):
                if not m.file:
                    continue
                fname = (getattr(m.file, 'name', '') or '').lower()
                caption = (m.text or '').lower()
                if not (fname.endswith('.mkv') or fname.endswith('.mp4')):
                    continue
                
                # Descartar falsos positivos
                combined = fname + " " + caption
                if not is_title_match(names, combined):
                    continue

                valid_files.append(m)
            if valid_files:
                break
        except Exception as e:
            print(f"Error buscando '{name}': {e}")
    return valid_files

async def main():
    # Usar SESSION_PROD para chequear Búnker y producción
    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client_prod:
        me = await client_prod.get_me()
        print(f"🔍 Conectado con SESSION_PROD: {me.first_name} (ID: {me.id})")

        # 1. Analizar Búnker SERIES TV
        print(f"\n📡 Analizando Búnker 'SERIES TV' ({BUNKER_SERIES})...")
        bunker_ent = await client_prod.get_entity(BUNKER_SERIES)
        bunker_topics = await get_all_topics(client_prod, bunker_ent)
        print(f"✅ Total temas en Búnker: {len(bunker_topics)}")

        results = []
        missing_series = []

        for item in TARGET_SERIES:
            serie_name = item["names"][0]
            matched_topic = None
            for t in bunker_topics:
                if is_title_match(item["names"], t.title):
                    matched_topic = t
                    break

            if matched_topic:
                c, mkv, mp4, other, samples = await count_files_in_topic(client_prod, bunker_ent, matched_topic.id)
                results.append({
                    "name": serie_name,
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
                    "name": serie_name,
                    "year": item["years"],
                    "status": "NO_EN_BUNKER",
                    "files_total": 0,
                    "mkv": 0,
                    "mp4": 0,
                    "other": 0,
                    "samples": []
                })

        print(f"📊 Encontradas en Búnker: {len(results) - len(missing_series)} / 30")

        # Canales TeVeFlipe (Retro, Clásicas, etc.) accesibles desde SESSION_PROD
        dialogs = await client_prod.get_dialogs(limit=100)
        teveflipe_chats = [d.entity for d in dialogs if d.id not in [BUNKER_SERIES, PROD_SERIES] and any(k in normalize(d.title) for k in ["retro", "clasicas", "demo"])]

        for m_item in missing_series:
            m_res = next(r for r in results if r["name"] == m_item["names"][0])
            for chat in teveflipe_chats:
                if m_res.get("found_in_community"):
                    break
                files = await search_files(client_prod, chat, m_item["names"])
                if files:
                    m_res["found_in_community"] = True
                    m_res["comm_chat_title"] = getattr(chat, 'title', str(chat.id))
                    m_res["comm_files"] = len(files)
                    m_res["comm_mkv"] = sum(1 for m in files if (m.file.name or '').lower().endswith('.mkv'))
                    m_res["comm_mp4"] = sum(1 for m in files if (m.file.name or '').lower().endswith('.mp4'))
                    m_res["comm_samples"] = [m.file.name for m in files[:2]]
                    print(f"   🎯 Localizada '{m_item['names'][0]}' en '{chat.title}': {len(files)} caps ({m_res['comm_mkv']} mkv, {m_res['comm_mp4']} mp4)")

    # 2. Intentar buscar en Comunidad Castellana con TELEGRAM_STRING_SESSION
    if TELEGRAM_STRING_SESSION:
        print("\n📡 Conectando con TELEGRAM_STRING_SESSION para explorar Series Comunidad Castellana (-1002257262928)...")
        try:
            async with TelegramClient(StringSession(TELEGRAM_STRING_SESSION), API_ID, API_HASH) as client_comm:
                me_comm = await client_comm.get_me()
                print(f"✅ Conectado con sesión secundaria: {me_comm.first_name} (ID: {me_comm.id})")
                
                comm_ent = await client_comm.get_entity(COMMUNITY_SERIES_CHAT)
                print(f"✅ Acceso exitoso a '{comm_ent.title}' ({comm_ent.id})")

                # Explorar temas 157592 (Series Completas) y 470115 (Emisión)
                for m_item in missing_series:
                    m_res = next(r for r in results if r["name"] == m_item["names"][0])
                    if m_res.get("found_in_community"):
                        continue
                    
                    for top_id in [157592, 470115, None]:
                        files = await search_files(client_comm, comm_ent, m_item["names"], topic_id=top_id)
                        if files:
                            m_res["found_in_community"] = True
                            m_res["comm_chat_title"] = f"Series Comunidad Castellana ({'Completas' if top_id==157592 else ('Emisión' if top_id==470115 else 'General')})"
                            m_res["comm_files"] = len(files)
                            m_res["comm_mkv"] = sum(1 for m in files if (m.file.name or '').lower().endswith('.mkv'))
                            m_res["comm_mp4"] = sum(1 for m in files if (m.file.name or '').lower().endswith('.mp4'))
                            m_res["comm_samples"] = [m.file.name for m in files[:2]]
                            print(f"   🎯 Localizada '{m_item['names'][0]}' en Comunidad Castellana: {len(files)} caps ({m_res['comm_mkv']} mkv, {m_res['comm_mp4']} mp4)")
                            break
        except Exception as e:
            print(f"⚠️ No se pudo explorar con TELEGRAM_STRING_SESSION: {e}")

    # 3. Presentación estructurada del informe
    print("\n" + "="*85)
    print("INFORME DE AUDITORÍA: 30 SERIES IMPRESCINDIBLES DEL SIGLO XXI")
    print("="*85)
    bunker_count = sum(1 for r in results if r["status"] == "DISPONIBLE_BUNKER")
    comm_count = sum(1 for r in results if r.get("found_in_community"))
    not_found_count = 30 - bunker_count - comm_count

    print(f"Resumen General:")
    print(f"  • En el Búnker SERIES TV: {bunker_count} / 30")
    print(f"  • En Comunidad Castellana / Canales fuente: {comm_count} / 30")
    print(f"  • Pendientes de localizar: {not_found_count} / 30\n")

    for idx, r in enumerate(results, 1):
        if r["status"] == "DISPONIBLE_BUNKER":
            fmt = f"MKV: {r['mkv']}, MP4: {r['mp4']}"
            if r['other'] > 0:
                fmt += f", Otros: {r['other']}"
            print(f"{idx:2d}. [EN BÚNKER] {r['name']} ({r['year']})")
            print(f"    Tema: \"{r['bunker_topic_title']}\" (ID: {r['bunker_topic_id']})")
            print(f"    Capítulos: {r['files_total']} ({fmt})")
            if r['samples']:
                print(f"    Muestra: {r['samples'][:2]}")
        elif r.get("found_in_community"):
            fmt = f"MKV: {r['comm_mkv']}, MP4: {r['comm_mp4']}"
            print(f"{idx:2d}. [DISPONIBLE EN COMUNIDAD] {r['name']} ({r['year']})")
            print(f"    Origen: \"{r['comm_chat_title']}\"")
            print(f"    Capítulos: {r['comm_files']} ({fmt})")
            if r['comm_samples']:
                print(f"    Muestra: {r['comm_samples'][:2]}")
        else:
            print(f"{idx:2d}. [NO LOCALIZADA] {r['name']} ({r['year']})")
            print(f"    No se encontró disponible en formato MKV/MP4.")

    print("="*85)

if __name__ == "__main__":
    asyncio.run(main())
