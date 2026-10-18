import asyncio
import os
import json
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import ChannelParticipantsAdmins, ChannelParticipantsKicked, ChannelParticipantsBanned
from telethon.tl.functions.channels import GetParticipantRequest

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")

# Canales externos que sabemos que NO son búnkers propios de Felipe:
EXTERNAL_CHATS = {-1001905652210, -1003567099600}

async def main():
    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client:
        me = await client.get_me()
        print(f"Cuenta autenticada: {me.first_name} (ID: {me.id}, Username: @{me.username})")

        with open("canales_map.json", "r", encoding="utf-8") as f:
            canales = json.load(f)

        print("\n" + "="*80)
        print("AUDITORÍA DE ROLES Y MIEMBROS EN CANALES BÚNKER")
        print("="*80)

        for c in canales:
            b_id = c.get("bunker_id")
            b_nombre = c.get("bunker_nombre", c.get("nombre"))

            if b_id in EXTERNAL_CHATS:
                print(f"\n⏩ Saltando canal externo: {b_nombre} ({b_id})")
                continue

            print(f"\n🔍 Analizando Búnker: {b_nombre} (ID: {b_id})")
            try:
                entity = await client.get_entity(b_id)
                # Obtener nuestro participante
                try:
                    p = await client(GetParticipantRequest(channel=entity, participant=me))
                    participant_type = type(p.participant).__name__
                    is_admin = participant_type in ["ChannelParticipantAdmin", "ChannelParticipantCreator"]
                    admin_rights = getattr(p.participant, "admin_rights", None)
                    can_ban = getattr(admin_rights, "ban_users", False) if admin_rights else (participant_type == "ChannelParticipantCreator")
                    can_change_info = getattr(admin_rights, "change_info", False) if admin_rights else (participant_type == "ChannelParticipantCreator")
                    can_invite = getattr(admin_rights, "invite_users", False) if admin_rights else (participant_type == "ChannelParticipantCreator")
                    
                    print(f"   Rol de la sesión: {participant_type}")
                    print(f"   Permisos: ban={can_ban}, change_info={can_change_info}, invite={can_invite}")
                except Exception as pe:
                    print(f"   ⚠️ No se pudo obtener rol individual: {pe}")
                    can_ban = False

                # Contar participantes totales
                try:
                    participants = await client.get_participants(entity, limit=200)
                    total_count = len(participants)
                    print(f"   Total miembros encontrados: {total_count}")
                    
                    admins = []
                    users = []
                    for m in participants:
                        name = f"{m.first_name or ''} {m.last_name or ''}".strip()
                        if m.bot:
                            admins.append(f"[BOT] {name} (ID: {m.id})")
                        elif m.id == me.id:
                            admins.append(f"[TÚ] {name} (ID: {m.id})")
                        else:
                            users.append(f"{name} (ID: {m.id}, @{m.username})")

                    print(f"   Admins/Bots/Tú ({len(admins)}): {admins}")
                    print(f"   Usuarios ajenos ({len(users)}): {users[:10]} {'...' if len(users) > 10 else ''}")
                except Exception as e:
                    print(f"   ⚠️ No se pudo listar participantes: {e}")

            except Exception as e:
                print(f"   ❌ Error accediendo al búnker {b_id}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
