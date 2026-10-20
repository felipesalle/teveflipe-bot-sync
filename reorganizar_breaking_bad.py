import asyncio
import os
import re
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ForwardMessagesRequest, DeleteMessagesRequest

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")
TELEGRAM_STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION", "")

BUNKER_SERIES = -1002097175258
RETRO_SERIES = -1003865750796
COMMUNITY_SERIES = -1002257262928
TOPIC_BB = 27949

def parse_episode_sort_key(filename: str):
    m = re.search(r'(?:(\d{1,2})\s*x\s*(\d{1,2})|[sS](\d{1,2})[._\s]*[eE](\d{1,2}))', filename)
    if m:
        season = int(m.group(1) or m.group(3))
        episode = int(m.group(2) or m.group(4))
        return (season, episode)
    m2 = re.search(r'\b(\d{1,2})(\d{2})\b', filename)
    if m2:
        return (int(m2.group(1)), int(m2.group(2)))
    return (99, 99)

# Número oficial de capítulos por temporada en Breaking Bad
OFFICIAL_SEASONS = {
    1: 7,
    2: 13,
    3: 13,
    4: 13,
    5: 16
}

async def main():
    print("🚀 INICIANDO SANEAMIENTO Y ORDENAMIENTO DE BREAKING BAD EN BÚNKER")
    client_prod = TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH)
    client_comm = TelegramClient(StringSession(TELEGRAM_STRING_SESSION), API_ID, API_HASH)

    await client_prod.connect()
    await client_comm.connect()

    bunker_prod = await client_prod.get_entity(BUNKER_SERIES)
    retro_ent = await client_prod.get_entity(RETRO_SERIES)
    comm_ent = await client_comm.get_entity(COMMUNITY_SERIES)

    # 1. Borrar episodios actuales con desorden en Topic 27949
    print(f"\n1. Inspeccionando mensajes existentes en Topic {TOPIC_BB}...")
    msgs_to_delete = []
    async for m in client_prod.iter_messages(bunker_prod, reply_to=TOPIC_BB):
        # Borrar todos los archivos de video en el topic (dejando la sinopsis si es puro texto)
        if m.id != TOPIC_BB and m.file:
            msgs_to_delete.append(m.id)

    print(f"   Encontrados {len(msgs_to_delete)} mensajes de video para eliminar del Topic {TOPIC_BB}.")
    if msgs_to_delete:
        for i in range(0, len(msgs_to_delete), 50):
            chunk = msgs_to_delete[i:i+50]
            await client_prod.delete_messages(bunker_prod, chunk)
            await asyncio.sleep(1)
        print("   ✓ Episodios anteriores eliminados correctamente.")

    # 2. Recolectar episodios candidatos desde Retro y Comunidad
    print("\n2. Recolectando episodios desde canales fuente...")
    candidates = {} # (season, ep): {'id': ..., 'fn': ..., 'source': ..., 'client': ...}

    # Desde Retro:
    async for m in client_prod.iter_messages(retro_ent, search="Breaking Bad", limit=200):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if fn.lower().endswith(('.mkv', '.mp4')) and 'breaking bad' in fn.lower():
                s, e = parse_episode_sort_key(fn)
                if 1 <= s <= 5 and 1 <= e <= OFFICIAL_SEASONS.get(s, 0):
                    # Preferimos Newpct1 / 1080p si hay duplicados
                    current = candidates.get((s, e))
                    is_newpct1 = 'newpct1' in fn.lower() or 'm1080' in fn.lower()
                    if not current or (is_newpct1 and 'newpct1' not in current['fn'].lower()):
                        candidates[(s, e)] = {
                            'id': m.id,
                            'fn': fn,
                            'source': retro_ent,
                            'client': client_prod,
                            'to_peer': bunker_prod
                        }

    # Desde Comunidad Castellana (especialmente para Temporada 5 impecable):
    async for m in client_comm.iter_messages(comm_ent, search="Breaking Bad", limit=100):
        if m.file:
            fn = getattr(m.file, 'name', '') or ''
            if fn.lower().endswith(('.mkv', '.mp4')) and 'breaking bad' in fn.lower():
                s, e = parse_episode_sort_key(fn)
                if 1 <= s <= 5 and 1 <= e <= OFFICIAL_SEASONS.get(s, 0):
                    current = candidates.get((s, e))
                    is_newpct1 = 'newpct1' in fn.lower() or 'm1080' in fn.lower()
                    if not current or (is_newpct1 and 'newpct1' not in current['fn'].lower()):
                        candidates[(s, e)] = {
                            'id': m.id,
                            'fn': fn,
                            'source': comm_ent,
                            'client': client_comm,
                            'to_peer': await client_comm.get_entity(BUNKER_SERIES)
                        }

    print(f"   Episodios únicos identificados: {len(candidates)} / 62 oficiales.")

    # Verificar si falta alguno
    missing = []
    for s in sorted(OFFICIAL_SEASONS.keys()):
        for e in range(1, OFFICIAL_SEASONS[s] + 1):
            if (s, e) not in candidates:
                missing.append((s, e))

    if missing:
        print(f"⚠️ ATENCIÓN: Faltan {len(missing)} episodios: {missing}")
    else:
        print("   ✓ Todos los 62 episodios de las 5 temporadas están presentes y localizados.")

    # 3. Enviar episodios en orden cronológico estricto (1x01 -> 5x16) uno a uno
    sorted_keys = sorted(candidates.keys())
    print(f"\n3. Reenviando {len(sorted_keys)} episodios en orden cronológico uno a uno...")

    for idx, (s, e) in enumerate(sorted_keys, 1):
        item = candidates[(s, e)]
        client = item['client']
        source = item['source']
        to_peer = item['to_peer']
        msg_id = item['id']
        fn = item['fn']

        # Enviar 1 a 1 para asegurar orden estricto de IDs en Telegram
        await client(ForwardMessagesRequest(
            from_peer=source,
            to_peer=to_peer,
            id=[msg_id],
            top_msg_id=TOPIC_BB,
            drop_author=True
        ))
        print(f"   [{idx:2d}/62] Reenviado T{s:02d}E{e:02d}: {fn}")
        await asyncio.sleep(1.2) # Pausa para mantener orden y respetar rate limit

    print("\n🎉 ¡BREAKING BAD HA SIDO REORGANIZADA DE FORMA IMPECABLE!")
    await client_prod.disconnect()
    await client_comm.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
