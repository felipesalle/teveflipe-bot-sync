import asyncio
import os
import sys
from telethon import TelegramClient, utils
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ForwardMessagesRequest, CreateForumTopicRequest

sys.stdout.reconfigure(encoding='utf-8')

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION = os.environ["TELEGRAM_STRING_SESSION"]

SAGAS_GROUP_ID = -1003913363596

# Lista de Sagas con sus películas ordenadas cronológicamente
# Cada elemento es (chat_origen, msg_id, titulo_display)
SAGAS_PLAN = [
    {
        "topic": "⚡ Harry Potter",
        "icon_color": 0x5AC8FA, # blue
        "movies": [
            (-1003763464899, 926, "1. Harry Potter y la piedra filosofal (2001)"),
            (-1003763464899, 927, "2. Harry Potter y la cámara secreta (2002)"),
            (-1003763464899, 928, "3. Harry Potter y el prisionero de Azkaban (2004)"),
            (-1003763464899, 929, "4. Harry Potter y el cáliz de fuego (2005)"),
            (-1003763464899, 930, "5. Harry Potter y la Orden del Fénix / Príncipe (2009)"),
            (-1003763464899, 931, "6. Harry Potter y las reliquias de la muerte - Parte 1 (2010)"),
            (-1003763464899, 932, "7. Harry Potter y las reliquias de la muerte - Parte 2 (2011)"),
        ]
    },
    {
        "topic": "💍 El Señor de los Anillos",
        "icon_color": 0xFFCC00, # gold
        "movies": [
            (-1003763464899, 97, "1. El Señor de los Anillos: La comunidad del anillo (2001)"),
            (-1003763464899, 98, "2. El Señor de los Anillos: Las dos torres (2002)"),
            (-1003763464899, 100, "3. El Señor de los Anillos: El retorno del rey (2003)"),
        ]
    },
    {
        "topic": "🤠 Indiana Jones",
        "icon_color": 0xFF9500, # orange
        "movies": [
            (-1003763464899, 1571, "1. En busca del arca perdida (1981)"),
            (-1003763464899, 1573, "2. Indiana Jones y el templo maldito (1984)"),
            (-1003763464899, 1575, "3. Indiana Jones y la última cruzada (1989)"),
            (-1003763464899, 1576, "4. Indiana Jones y el reino de la calavera de cristal (2008)"),
            (-1003763464899, 1578, "5. Indiana Jones y el dial del destino (2023)"),
        ]
    },
    {
        "topic": "🕶️ Matrix",
        "icon_color": 0x4CD964, # green
        "movies": [
            (-1004467288762, 256, "1. Matrix (1999)"),
            (-1003763464899, 470, "2. Matrix Reloaded (2003)"),
            (-1003763464899, 471, "3. Matrix Revolutions (2003)"),
        ]
    },
    {
        "topic": "🌹 El Padrino",
        "icon_color": 0x8E8E93, # gray
        "movies": [
            (-1003763464899, 316, "1. El padrino (1972)"),
            (-1003763464899, 318, "2. El padrino II (1974)"),
            (-1003763464899, 320, "3. El padrino III (1990)"),
        ]
    },
    {
        "topic": "🚗 Regreso al Futuro",
        "icon_color": 0x007AFF, # blue
        "movies": [
            (-1003763464899, 450, "1. Regreso al futuro (1985)"),
            (-1003763464899, 451, "2. Regreso al futuro II (1989)"),
            (-1003763464899, 367, "3. Regreso al futuro III (1990)"),
        ]
    },
    {
        "topic": "🎯 Jason Bourne",
        "icon_color": 0x5856D6, # purple
        "movies": [
            (-1003763464899, 1384, "1. El caso Bourne (2002)"),
            (-1003763464899, 1385, "2. El mito de Bourne (2004)"),
            (-1003763464899, 1386, "3. El ultimátum de Bourne (2007)"),
            (-1003763464899, 1387, "4. El legado de Bourne (2012)"),
            (-1003763464899, 1388, "5. Jason Bourne (2016)"),
        ]
    },
    {
        "topic": "🏹 Los Juegos del Hambre",
        "icon_color": 0xFF3B30, # red
        "movies": [
            (-1003763464899, 914, "1. Los juegos del hambre (2012)"),
            (-1003763464899, 915, "2. Los juegos del hambre: En llamas (2013)"),
            (-1003763464899, 916, "3. Los juegos del hambre: Sinsajo - Parte 1 (2014)"),
            (-1003763464899, 917, "4. Los juegos del hambre: Sinsajo - Parte 2 (2015)"),
        ]
    },
    {
        "topic": "🦾 Terminator",
        "icon_color": 0x8E8E93, # gray
        "movies": [
            (-1003763464899, 280, "1. Terminator (1984)"),
            (-1003763464899, 282, "2. Terminator 2: El juicio final (1991)"),
            (-1003763464899, 288, "3. Terminator 3: La rebelión de las máquinas (2003)"),
            (-1003763464899, 285, "4. Terminator 4: Salvation (2009)"),
        ]
    },
    {
        "topic": "🪖 Rambo",
        "icon_color": 0x4CD964, # green
        "movies": [
            (-1003763464899, 1492, "1. Rambo: Acorralado (1982)"),
            (-1003763464899, 1494, "2. Rambo: Acorralado Parte II (1985)"),
            (-1003763464899, 1496, "3. Rambo III (1988)"),
            (-1003763464899, 1498, "4. Rambo IV (John Rambo) (2008)"),
        ]
    },
    {
        "topic": "🥊 Rocky Balboa",
        "icon_color": 0xFF9500, # orange
        "movies": [
            (-1003763464899, 542, "1. Rocky (1976)"),
            (-1003763464899, 543, "2. Rocky II (1979)"),
            (-1003763464899, 544, "3. Rocky III (1982)"),
            (-1004467288762, 4391, "4. Rocky IV (1985)"),
            (-1003763464899, 545, "5. Rocky V (1990)"),
            (-1003763464899, 546, "6. Rocky Balboa (2006)"),
        ]
    },
    {
        "topic": "🔫 Arma Letal",
        "icon_color": 0x007AFF, # blue
        "movies": [
            (-1003763464899, 498, "1. Arma letal (1987)"),
            (-1003763464899, 499, "2. Arma letal 2 (1989)"),
            (-1003763464899, 500, "3. Arma letal 3 (1992)"),
            (-1003763464899, 501, "4. Arma letal 4 (1998)"),
        ]
    },
    {
        "topic": "🦖 Parque Jurásico",
        "icon_color": 0x4CD964, # green
        "movies": [
            (-1003763464899, 513, "1. Parque Jurásico (1993)"),
            (-1003763464899, 514, "2. El mundo perdido: Jurassic Park (1997)"),
            (-1003763464899, 515, "3. Parque Jurásico III (2001)"),
        ]
    },
    {
        "topic": "👹 Shrek",
        "icon_color": 0x4CD964, # green
        "movies": [
            (-1004326583216, 342, "1. Shrek (2001)"),
            (-1004326583216, 343, "2. Shrek 2 (2004)"),
            (-1004326583216, 344, "3. Shrek Tercero (2007)"),
            (-1004326583216, 345, "4. Shrek, felices para siempre (2010)"),
        ]
    },
    {
        "topic": "🦇 Batman (Saga Clásica & Nolan)",
        "icon_color": 0x8E8E93, # gray
        "movies": [
            (-1004467288762, 3071, "1. Batman (1989)"),
            (-1003763464899, 1520, "2. Batman Returns (1992)"),
            (-1003763464899, 1521, "3. Batman Forever (1995)"),
            (-1003763464899, 1523, "4. Batman y Robin (1997)"),
            (-1003763464899, 1525, "5. Batman Begins (2005)"),
            (-1003763464899, 1527, "6. El Caballero Oscuro (2008)"),
            (-1003763464899, 1529, "7. El Caballero Oscuro: La leyenda renace (2012)"),
            (-1003763464899, 1531, "8. The Batman (2022)"),
        ]
    },
    {
        "topic": "🏎️ Mad Max",
        "icon_color": 0xFF9500, # orange
        "movies": [
            (-1003763464899, 638, "1. Mad Max: Salvajes de autopista (1979)"),
            (-1003763464899, 639, "2. Mad Max 2: El guerrero de la carretera (1981)"),
            (-1003763464899, 640, "3. Mad Max 3: Más allá de la cúpula del trueno (1985)"),
        ]
    },
    {
        "topic": "🦁 El Rey León",
        "icon_color": 0xFFCC00, # gold
        "movies": [
            (-1004326583216, 257, "1. El Rey León (1994)"),
            (-1004467288762, 4861, "2. El Rey León II: El tesoro de Simba (1998)"),
            (-1004326583216, 258, "3. El Rey León 3: Hakuna Matata (2004)"),
        ]
    },
    {
        "topic": "❄️ La Era de Hielo (Ice Age)",
        "icon_color": 0x5AC8FA, # light blue
        "movies": [
            (-1004326583216, 171, "1. La Era de Hielo 2 (2006)"),
            (-1004326583216, 172, "2. La Era de Hielo 3 (2009)"),
            (-1004326583216, 174, "3. La Era de Hielo 4: La deriva continental (2012)"),
            (-1004326583216, 176, "4. La Era de Hielo 5: Choque de mundos (2016)"),
        ]
    },
    {
        "topic": "🟡 Gru: Mi Villano Favorito & Minions",
        "icon_color": 0xFFCC00, # yellow
        "movies": [
            (-1004326583216, 402, "1. Gru, Mi villano favorito (2010)"),
            (-1004326583216, 403, "2. Gru 2, Mi villano favorito (2013)"),
            (-1004326583216, 404, "3. Los Minions (2015)"),
            (-1004326583216, 405, "4. Gru 3, Mi villano favorito (2017)"),
            (-1004326583216, 406, "5. Minions: El origen de Gru (2022)"),
            (-1004326583216, 407, "6. Gru 4, Mi villano favorito (2024)"),
        ]
    },
    {
        "topic": "🩸 Pesadilla en Elm Street",
        "icon_color": 0xFF3B30, # red
        "movies": [
            (-1004467288762, 189, "1. Pesadilla en Elm Street (1984)"),
            (-1004467288762, 3538, "2. Pesadilla en Elm Street 2: La venganza de Freddy (1985)"),
            (-1004467288762, 3537, "3. Pesadilla en Elm Street 3: Los guerreros del sueño (1987)"),
            (-1004467288762, 3536, "4. Pesadilla en Elm Street 4: El amo del sueño (1988)"),
            (-1004467288762, 3535, "5. Pesadilla en Elm Street 5: El niño de los sueños (1989)"),
        ]
    },
    {
        "topic": "🏒 Viernes 13 (Jason Voorhees)",
        "icon_color": 0x8E8E93, # gray
        "movies": [
            (-1004467288762, 2412, "1. Viernes 13: Parte 2 (1981)"),
            (-1004467288762, 2411, "2. Viernes 13: Parte 3 (1982)"),
            (-1004467288762, 2410, "3. Viernes 13: Parte 4 - Último capítulo (1984)"),
            (-1004467288762, 2409, "4. Viernes 13: Parte 5 - Un nuevo comienzo (1985)"),
            (-1004467288762, 2408, "5. Viernes 13: Parte 6 - Jason vive (1986)"),
            (-1004467288762, 2407, "6. Viernes 13: Parte 7 - Sangre nueva (1988)"),
            (-1004467288762, 2406, "7. Viernes 13: Parte 8 - Jason toma Manhattan (1989)"),
            (-1004467288762, 2405, "8. Viernes 13: Parte 9 - Jason se va al infierno (1993)"),
        ]
    },
    {
        "topic": "🎃 Halloween (Michael Myers)",
        "icon_color": 0xFF9500, # orange
        "movies": [
            (-1004467288762, 2816, "1. Halloween II: Sanguinario (1981)"),
            (-1004467288762, 2815, "2. Halloween III: El día de la bruja (1982)"),
            (-1004467288762, 2814, "3. Halloween 4: El regreso de Michael Myers (1988)"),
            (-1004467288762, 2813, "4. Halloween 5: La venganza de Michael Myers (1989)"),
            (-1004467288762, 2812, "5. Halloween 6: La maldición de Michael Myers (1995)"),
        ]
    },
    {
        "topic": "⛓️ Hellraiser",
        "icon_color": 0x5856D6, # purple
        "movies": [
            (-1004467288762, 2738, "1. Hellraiser (1987)"),
            (-1004467288762, 2737, "2. Hellraiser II: Hellbound (1988)"),
            (-1004467288762, 2736, "3. Hellraiser III: Infierno en la Tierra (1992)"),
            (-1004467288762, 2735, "4. Hellraiser IV: Bloodline (1996)"),
        ]
    },
    {
        "topic": "🔪 Muñeco Diabólico (Chucky)",
        "icon_color": 0xFF3B30, # red
        "movies": [
            (-1004467288762, 103, "1. Muñeco diabólico (1988)"),
            (-1004467288762, 102, "2. Muñeco diabólico 2 (1990)"),
            (-1004467288762, 101, "3. Muñeco diabólico 3 (1991)"),
            (-1004467288762, 2426, "4. La novia de Chucky (1998)"),
        ]
    },
    {
        "topic": "🦈 Tiburón (Jaws)",
        "icon_color": 0x007AFF, # blue
        "movies": [
            (-1003763464899, 558, "1. Tiburón (1975)"),
            (-1003763464899, 559, "2. Tiburón 2 (1978)"),
            (-1004467288762, 4820, "3. Tiburón 3-D (1983)"),
            (-1004467288762, 4818, "4. Tiburón 4: La venganza (1987)"),
        ]
    },
    {
        "topic": "🥋 Karate Kid",
        "icon_color": 0xFF9500, # orange
        "movies": [
            (-1003763464899, 522, "1. Karate Kid: El momento de la verdad (1984)"),
            (-1003763464899, 523, "2. Karate Kid II: La historia continúa (1986)"),
            (-1003763464899, 524, "3. Karate Kid III: El desafío final (1989)"),
            (-1004467288762, 4981, "4. El nuevo Karate Kid (1994)"),
        ]
    },
    {
        "topic": "👮 Loca Academia de Policía",
        "icon_color": 0x007AFF, # blue
        "movies": [
            (-1004467288762, 1608, "1. Loca academia de policía (1984)"),
            (-1004467288762, 1607, "2. Loca academia de policía 2: Su primera misión (1985)"),
            (-1004467288762, 1606, "3. Loca academia de policía 3: De vuelta a la escuela (1986)"),
            (-1004467288762, 1605, "4. Loca academia de policía 4: Los ciudadanos se defienden (1987)"),
            (-1004467288762, 1604, "5. Loca academia de policía 5: Operación Miami Beach (1988)"),
            (-1004467288762, 1603, "6. Loca academia de policía 6: Ciudad sitiada (1989)"),
        ]
    },
    {
        "topic": "🕶️ Superdetective en Hollywood",
        "icon_color": 0x5856D6, # purple
        "movies": [
            (-1003763464899, 533, "1. Superdetective en Hollywood (1984)"),
            (-1003763464899, 534, "2. Superdetective en Hollywood II (1987)"),
            (-1003763464899, 535, "3. Superdetective en Hollywood III (1994)"),
            (-1003763464899, 1400, "4. Superdetective en Hollywood: Axel F (2024)"),
        ]
    },
    {
        "topic": "🐊 Cocodrilo Dundee",
        "icon_color": 0x4CD964, # green
        "movies": [
            (-1003763464899, 1560, "1. Cocodrilo Dundee (1986)"),
            (-1003763464899, 1562, "2. Cocodrilo Dundee II (1988)"),
            (-1003763464899, 1564, "3. Cocodrilo Dundee en Los Ángeles (2001)"),
        ]
    },
    {
        "topic": "🗡️ Blade (El Cazavampiros)",
        "icon_color": 0x8E8E93, # gray
        "movies": [
            (-1003763464899, 588, "1. Blade (1998)"),
            (-1003763464899, 589, "2. Blade II (2002)"),
            (-1003763464899, 590, "3. Blade: Trinity (2004)"),
        ]
    },
    {
        "topic": "👾 Gremlins",
        "icon_color": 0x4CD964, # green
        "movies": [
            (-1003763464899, 516, "1. Gremlins (1984)"),
            (-1003763464899, 517, "2. Gremlins 2: La nueva generación (1990)"),
        ]
    },
    {
        "topic": "🐉 La Historia Interminable",
        "icon_color": 0x5AC8FA, # blue
        "movies": [
            (-1003763464899, 1566, "1. La historia interminable (1984)"),
            (-1004467288762, 4004, "2. La historia interminable II: El siguiente capítulo (1990)"),
            (-1004467288762, 1914, "3. La historia interminable 3 (1994)"),
        ]
    },
    {
        "topic": "🕵️ Agárralo como puedas",
        "icon_color": 0x007AFF, # blue
        "movies": [
            (-1004467288762, 4177, "1. Agárralo como puedas (1988)"),
            (-1004467288762, 4176, "2. Agárralo como puedas 2½: El aroma del miedo (1991)"),
            (-1004467288762, 4175, "3. Agárralo como puedas 33⅓: El insulto final (1994)"),
        ]
    },
    {
        "topic": "✈️ Aterriza como puedas",
        "icon_color": 0x5AC8FA, # light blue
        "movies": [
            (-1004467288762, 4280, "1. Aterriza como puedas (1980)"),
            (-1004467288762, 4279, "2. Aterriza como puedas II (1982)"),
        ]
    },
    {
        "topic": "🕵️ Misión Imposible",
        "icon_color": 0xFF3B30, # red
        "movies": [
            (-1003763464899, 593, "1. Misión Imposible (1996)"),
            (-1003763464899, 594, "2. Misión Imposible 2 (2000)"),
            (-1003763464899, 595, "3. Misión Imposible 3 (2006)"),
            (-1002146236969, 684, "4. Misión Imposible: Protocolo Fantasma (2011)"),
        ]
    }
]

async def main():
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        # Pre-cargar entidades desde los diálogos de la sesión para evitar "Could not find the input entity"
        print("🔄 Cargando lista de diálogos para poblar caché de entidades...")
        dialogs = await client.get_dialogs(limit=200)
        entity_cache = {}
        for d in dialogs:
            entity_cache[d.id] = d.entity
            entity_cache[utils.get_peer_id(d.entity)] = d.entity
        print(f"✅ Diálogos cargados ({len(dialogs)} encontrados).")

        # Resolver y asegurar acceso a los canales de origen usando invite links o get_entity
        from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest
        from telethon.tl.types import ChatInviteAlready
        channel_invites = {
            -1003763464899: "VpmsvyK63OplZGIx", # Estrenos
            -1004467288762: "qNjPZZ7F5hFmYmRh", # 80 y 90
            -1004326583216: "FTpg2qBHORMwNTNh", # Infantiles
            -1003886841797: "odH9vFdVUtMzOWNh", # Clásicas
        }
        for cid, inv_hash in channel_invites.items():
            if cid not in entity_cache:
                try:
                    check = await client(CheckChatInviteRequest(inv_hash))
                    if isinstance(check, ChatInviteAlready):
                        entity_cache[cid] = check.chat
                        entity_cache[utils.get_peer_id(check.chat)] = check.chat
                        print(f"✅ Canal {cid} resuelto vía invite existente: {getattr(check.chat, 'title', cid)}")
                    else:
                        imp = await client(ImportChatInviteRequest(inv_hash))
                        chat = imp.chats[0]
                        entity_cache[cid] = chat
                        entity_cache[utils.get_peer_id(chat)] = chat
                        print(f"✅ Canal {cid} unido vía invite: {getattr(chat, 'title', cid)}")
                except Exception as e:
                    print(f"⚠️ No se pudo resolver {cid} con invite {inv_hash}: {e}")
                    try:
                        ent = await client.get_entity(cid)
                        entity_cache[cid] = ent
                        entity_cache[utils.get_peer_id(ent)] = ent
                    except Exception as e2:
                        print(f"   ⚠️ Falló get_entity directo para {cid}: {e2}")

        target_group = entity_cache.get(SAGAS_GROUP_ID)
        if not target_group:
            target_group = await client.get_entity(SAGAS_GROUP_ID)
        print(f"🎯 Conectado al grupo destino: {target_group.title} (ID: {SAGAS_GROUP_ID})")

        # Comprobar temas existentes en el grupo de Sagas para no duplicar
        from telethon.tl.functions.messages import GetForumTopicsRequest
        existing_topics = {}
        try:
            res_topics = await client(GetForumTopicsRequest(
                peer=target_group,
                offset_date=None,
                offset_id=0,
                offset_topic=0,
                limit=100
            ))
            for t in res_topics.topics:
                existing_topics[t.title.strip().lower()] = t.id
            print(f"📋 Temas existentes en el grupo: {len(existing_topics)}")
        except Exception as e:
            print(f"⚠️ No se pudieron listar temas existentes: {e}")

        for saga in SAGAS_PLAN:
            topic_name = saga["topic"]
            topic_id = existing_topics.get(topic_name.strip().lower())
            
            if topic_id:
                print(f"\n📂 Tema existente detectado: '{topic_name}' (ID: {topic_id})")
            else:
                print(f"\n📁 Creando tema en foro: '{topic_name}'...")
                try:
                    res = await client(CreateForumTopicRequest(
                        peer=target_group,
                        title=topic_name,
                        icon_color=saga.get("icon_color", 0x5AC8FA)
                    ))
                    for update in res.updates:
                        if hasattr(update, 'message') and hasattr(update.message, 'id'):
                            topic_id = update.message.id
                            break
                        elif hasattr(update, 'id'):
                            topic_id = update.id
                            break
                    
                    if not topic_id:
                        print(f"⚠️ No se pudo obtener topic_id para {topic_name}, saltando.")
                        continue

                    print(f"✅ Tema creado con éxito! topic_id: {topic_id}")
                    await asyncio.sleep(2.0)
                except Exception as e:
                    print(f"❌ Error creando tema {topic_name}: {e}")
                    continue

            # 2. Comprobar si el tema ya tiene películas enviadas para no duplicar
            existing_msgs_in_topic = [m async for m in client.iter_messages(target_group, reply_to=topic_id, limit=5)]
            if len(existing_msgs_in_topic) >= len(saga["movies"]):
                print(f"⏩ El tema '{topic_name}' ya tiene {len(existing_msgs_in_topic)} mensajes. Saltando reenvío.")
                continue

            # Reenviar cada película al tema en orden cronológico
            from telethon.tl.functions.messages import ToggleNoForwardsRequest
            for chat_id, msg_id, display in saga["movies"]:
                try:
                    print(f"   🎬 Reenviando '{display}' (msg {msg_id} de {chat_id})...")
                    source_entity = entity_cache.get(chat_id)
                    if not source_entity:
                        source_entity = await client.get_entity(chat_id)
                    
                    # Intentar reenvío directo
                    try:
                        await client(ForwardMessagesRequest(
                            from_peer=source_entity,
                            id=[msg_id],
                            to_peer=target_group,
                            top_msg_id=topic_id,
                            drop_author=False
                        ))
                    except Exception as fe:
                        if "protected" in str(fe).lower() or "noforwards" in str(fe).lower():
                            print(f"   🔓 Desactivando temporalmente noforwards en canal {chat_id}...")
                            try:
                                await client(ToggleNoForwardsRequest(peer=source_entity, enabled=False))
                                await asyncio.sleep(1.5)
                                await client(ForwardMessagesRequest(
                                    from_peer=source_entity,
                                    id=[msg_id],
                                    to_peer=target_group,
                                    top_msg_id=topic_id,
                                    drop_author=False
                                ))
                                await client(ToggleNoForwardsRequest(peer=source_entity, enabled=True))
                            except Exception as fe2:
                                print(f"   ❌ No se pudo desactivar noforwards: {fe2}")
                                raise fe
                        else:
                            raise fe
                            
                    await asyncio.sleep(2.5) # Flood wait protection
                except Exception as e:
                    print(f"   ❌ Error reenviando película {msg_id}: {e}")
                    await asyncio.sleep(3.0)

            print(f"🎉 Saga '{topic_name}' completada ({len(saga['movies'])} películas).")
            await asyncio.sleep(3.0)

        print("\n🚀 ¡Todas las sagas iniciales han sido creadas y pobladas con éxito!")

if __name__ == "__main__":
    asyncio.run(main())
