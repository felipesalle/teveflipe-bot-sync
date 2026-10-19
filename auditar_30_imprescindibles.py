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
    
    # Descalificaciones específicas
    disallowed_map = {
        "the wire": ["wire in the blood"],
        "dark": ["matter", "winds", "angel", "skies", "shadows", "knight", "crystal", "justice", "runner"],
        "lost": ["space", "girl", "room", "canvas", "in the", "in space", "tapes", "dawson"],
        "arcane": ["league"],
        "the bear": ["masha", "grizzly", "bear in the big"],
        "fargo": [],
        "atlanta": [],
        "the americans": ["greatest", "horror", "pie", "gods", "dad", "crime"],
        "the office": ["uk", "australia", "india", "chile", "france"],
        "separacion": ["cinco grados", "dorama", "amor de verdad"],
        "gambito de dama": ["reglas del juego"],
        "hermanos de sangre": ["s04", "sangre de mi"],
    }

    for name in names:
        norm_name = normalize(name)
        if not norm_name:
            continue

        # Match exacto
        if norm_title == norm_name:
            return True

        # Descartar si contiene términos prohibidos
        if norm_name in disallowed_map:
            if any(dis in norm_title for dis in disallowed_map[norm_name]):
                continue

        # Búsqueda por límite de palabra
        pattern = r'(?:^|\b)' + re.escape(norm_name) + r'(?:\b|$)'
        if re.search(pattern, norm_title):
            # Para términos de 1 sola palabra corta
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

async def search_in_community_chat(client, chat_entity, names, target_topic_id=None):
    valid_files = []
    for name in names:
        try:
            # Buscar mensajes de documentos/videos con la query
            kwargs = {"search": name, "limit": 60}
            if target_topic_id:
                kwargs["reply_to"] = target_topic_id
            
            async for m in client.iter_messages(chat_entity, **kwargs):
                if not m.file:
                    continue
                fname = (getattr(m.file, 'name', '') or '').lower()
                caption = (m.text or '').lower()
                # Exclusivamente MKV o MP4
                if not (fname.endswith('.mkv') or fname.endswith('.mp4')):
                    continue
                
                # Comprobar si el archivo es realmente de la serie (evitar falsos positivos)
                combined = fname + " " + caption
                if not is_title_match(names, combined):
                    continue

                valid_files.append(m)
            
            if valid_files:
                break
        except Exception as e:
            print(f"Error buscando '{name}' en chat: {e}")
            
    return valid_files

async def main():
    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client:
        me = await client.get_me()
        print(f"🔍 Conectado como: {me.first_name} (ID: {me.id})")

        # 1. Analizar exhaustivamente el Búnker SERIES TV
        print(f"\n📡 Analizando Búnker 'SERIES TV' ({BUNKER_SERIES})...")
        bunker_ent = await client.get_entity(BUNKER_SERIES)
        bunker_topics = await get_all_topics(client, bunker_ent)
        print(f"✅ Total temas recuperados en Búnker: {len(bunker_topics)}")

        results = []
        missing_series = []

        for item in TARGET_SERIES:
            serie_name_main = item["names"][0]
            matched_topic = None
            
            # Buscar tema en Búnker
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
                print(f"   ✓ [BÚNKER] '{serie_name_main}' -> Tema '{matched_topic.title}' (ID {matched_topic.id}): {c} caps ({mkv} mkv, {mp4} mp4)")
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

        print(f"\n📊 Resumen Búnker: {len(results) - len(missing_series)} / 30 encontradas.")
        print(f"📊 Faltan en Búnker: {len(missing_series)} / 30.")

        # 2. Búsqueda en Comunidad Castellana para las faltantes
        print("\n📡 Analizando canales de Comunidad Castellana y repositorios fuente...")
        
        # Intentar acceder al canal de Series Comunidad Castellana (-1002257262928)
        comm_ent = None
        try:
            comm_ent = await client.get_entity(COMMUNITY_SERIES_CHAT)
            print(f"✅ Acceso confirmado a Series Comunidad Castellana: '{comm_ent.title}' ({comm_ent.id})")
        except Exception as e:
            print(f"⚠️ No se pudo resolver directamente {COMMUNITY_SERIES_CHAT} desde SESSION_PROD: {e}")

        # Otros canales disponibles en la cuenta
        dialogs = await client.get_dialogs(limit=150)
        source_candidates = []
        if comm_ent:
            source_candidates.append(comm_ent)
        for d in dialogs:
            if d.id in [BUNKER_SERIES, PROD_SERIES]:
                continue
            if comm_ent and d.id == comm_ent.id:
                continue
            t_norm = normalize(d.title)
            if any(k in t_norm for k in ["castellana", "series retro", "series clasicas", "comunidad", "demo"]):
                source_candidates.append(d.entity)

        print(f"Canales fuente a explorar: {len(source_candidates)}")

        for m_item in missing_series:
            m_res = next(r for r in results if r["name"] == m_item["names"][0])
            
            for src_chat in source_candidates:
                if m_res.get("found_in_community"):
                    break
                
                src_title = getattr(src_chat, 'title', str(src_chat.id))
                is_forum = getattr(src_chat, 'forum', False)
                
                # Si es foro (como -1002257262928), chequear topics relevantes primero
                if is_forum:
                    # En Comunidad Castellana, topic 157592 es SERIES COMPLETAS, 470115 es EMISIÓN
                    topics_to_search = [157592, 470115] if src_chat.id == COMMUNITY_SERIES_CHAT else [None]
                    for top_id in topics_to_search:
                        msgs = await search_in_community_chat(client, src_chat, m_item["names"], target_topic_id=top_id)
                        if msgs:
                            mkvs = sum(1 for m in msgs if (getattr(m.file, 'name', '') or '').lower().endswith('.mkv'))
                            mp4s = sum(1 for m in msgs if (getattr(m.file, 'name', '') or '').lower().endswith('.mp4'))
                            samples = [getattr(m.file, 'name', '') for m in msgs[:3]]
                            
                            m_res["found_in_community"] = True
                            m_res["comm_chat_id"] = src_chat.id
                            m_res["comm_chat_title"] = src_title
                            m_res["comm_topic_id"] = top_id
                            m_res["comm_topic_title"] = "SERIES COMPLETAS" if top_id == 157592 else ("EN EMISIÓN" if top_id == 470115 else "General")
                            m_res["comm_files"] = len(msgs)
                            m_res["comm_mkv"] = mkvs
                            m_res["comm_mp4"] = mp4s
                            m_res["comm_samples"] = samples
                            print(f"   🎯 [COMUNIDAD] '{m_item['names'][0]}' encontrada en '{src_title}' -> {len(msgs)} caps ({mkvs} mkv, {mp4s} mp4)")
                            break

                # Si no es foro o no apareció en los topics específicos, búsqueda general en el chat
                if not m_res.get("found_in_community"):
                    msgs = await search_in_community_chat(client, src_chat, m_item["names"])
                    if msgs:
                        mkvs = sum(1 for m in msgs if (getattr(m.file, 'name', '') or '').lower().endswith('.mkv'))
                        mp4s = sum(1 for m in msgs if (getattr(m.file, 'name', '') or '').lower().endswith('.mp4'))
                        samples = [getattr(m.file, 'name', '') for m in msgs[:3]]
                        
                        m_res["found_in_community"] = True
                        m_res["comm_chat_id"] = src_chat.id
                        m_res["comm_chat_title"] = src_title
                        m_res["comm_topic_id"] = None
                        m_res["comm_topic_title"] = "Chat General / Archivos"
                        m_res["comm_files"] = len(msgs)
                        m_res["comm_mkv"] = mkvs
                        m_res["comm_mp4"] = mp4s
                        m_res["comm_samples"] = samples
                        print(f"   🎯 [COMUNIDAD] '{m_item['names'][0]}' encontrada en '{src_title}' -> {len(msgs)} caps ({mkvs} mkv, {mp4s} mp4)")

        # 3. Presentación final del informe estructurado
        print("\n" + "="*85)
        print("INFORME DE AUDITORÍA: 30 SERIES IMPRESCINDIBLES DEL SIGLO XXI")
        print("="*85)
        
        bunker_count = sum(1 for r in results if r["status"] == "DISPONIBLE_BUNKER")
        comm_count = sum(1 for r in results if r.get("found_in_community"))
        missing_count = 30 - bunker_count - comm_count

        print(f"Resumen General:")
        print(f"  • Disponibles en el Búnker: {bunker_count} / 30")
        print(f"  • Localizadas en Comunidad Castellana / Canales fuente: {comm_count} / 30")
        print(f"  • Pendientes de localizar: {missing_count} / 30\n")

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
                print(f"    Canal: \"{r['comm_chat_title']}\" | Sección: \"{r['comm_topic_title']}\"")
                print(f"    Capítulos disponibles: {r['comm_files']} ({fmt})")
                if r['comm_samples']:
                    print(f"    Muestra: {r['comm_samples'][:2]}")
            else:
                print(f"{idx:2d}. [NO LOCALIZADA] {r['name']} ({r['year']})")
                print(f"    No se encontró actualmente con formato MKV/MP4.")

        print("="*85)

if __name__ == "__main__":
    asyncio.run(main())
