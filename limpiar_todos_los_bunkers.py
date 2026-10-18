import asyncio
import os
import json
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.functions.messages import (
    ToggleNoForwardsRequest,
    ExportChatInviteRequest,
    GetExportedChatInvitesRequest,
    EditExportedChatInviteRequest
)

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")

# Canales externos que NO son búnkers propios de Felipe:
EXTERNAL_CHATS = {-1001905652210, -1003567099600}

SAFE_USER_IDS = {
    6740086,     # Flipe loflipa (Felipe / Creador)
    7192044593,    # TeVeflipe (Bot / Sesión)
}

async def safe_sleep(secs: float):
    await asyncio.sleep(secs)

async def main():
    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client:
        me = await client.get_me()
        print(f"Cuenta autenticada: {me.first_name} (ID: {me.id})")
        SAFE_USER_IDS.add(me.id)

        with open("canales_map.json", "r", encoding="utf-8") as f:
            canales = json.load(f)

        print("\n" + "=" * 80)
        print("INICIANDO LIMPIEZA Y BLINDAJE DE TODOS LOS BÚNKERS")
        print("=" * 80)

        resumen_final = []

        for c in canales:
            b_id = c.get("bunker_id")
            b_nombre = c.get("bunker_nombre", c.get("nombre"))

            if b_id in EXTERNAL_CHATS:
                continue

            print(f"\n📁 PROCESANDO BÚNKER: {b_nombre} (ID: {b_id})")
            info_bunker = {
                "nombre": b_nombre,
                "id": b_id,
                "enlace_nuevo": None,
                "noforwards_ok": False,
                "expulsados": 0,
                "pendientes": 0,
                "total_restantes": 0
            }

            try:
                entity = await client.get_entity(b_id)

                # 1. Verificar admin
                try:
                    p = await client(GetParticipantRequest(channel=entity, participant=me))
                    p_type = type(p.participant).__name__
                    rights = getattr(p.participant, "admin_rights", None)
                    can_ban = getattr(rights, "ban_users", False) if rights else (p_type == "ChannelParticipantCreator")
                    print(f"   Rol: {p_type} | Permiso ban: {can_ban}")
                except Exception as pe:
                    print(f"   ⚠️ No se pudo comprobar rol: {pe}")
                    can_ban = False

                # 2. Desactivar noforwards
                try:
                    await client(ToggleNoForwardsRequest(peer=entity, enabled=False))
                    print("   🔓 'noforwards' desactivado.")
                    info_bunker["noforwards_ok"] = True
                except Exception as e:
                    print(f"   ℹ️ noforwards: {e}")

                # 3. Revocar enlace viejo y generar uno nuevo privado
                try:
                    new_invite = await client(ExportChatInviteRequest(peer=entity))
                    info_bunker["enlace_nuevo"] = getattr(new_invite, "link", "creado")
                    print(f"   🔒 Enlace revocado. Nuevo enlace privado: {info_bunker['enlace_nuevo']}")
                except Exception as e:
                    print(f"   ⚠️ Error gestionando enlaces: {e}")

                # 4. Expulsar usuarios ajenos
                if can_ban:
                    participants = await client.get_participants(entity, limit=500)
                    to_remove = [u for u in participants if u.id not in SAFE_USER_IDS and not u.bot]
                    print(f"   Total miembros actuales: {len(participants)} (Ajenos a expulsar: {len(to_remove)})")

                    exp_count = 0
                    skip_channel = False
                    for i, u in enumerate(to_remove, start=1):
                        uname = f"{u.first_name or ''} {u.last_name or ''}".strip() or f"User_{u.id}"
                        try:
                            await client.kick_participant(entity, u)
                            exp_count += 1
                            print(f"      [{i}/{len(to_remove)}] Expulsado: {uname}")
                            await safe_sleep(0.6)
                        except errors.FloodWaitError as fe:
                            print(f"      ⏳ FloodWait de {fe.seconds}s detectado.")
                            if fe.seconds > 60:
                                print(f"      ⏩ FloodWait largo ({fe.seconds}s). Dejando {len(to_remove) - exp_count} pendientes para siguiente tanda.")
                                info_bunker["pendientes"] = len(to_remove) - exp_count
                                skip_channel = True
                                break
                            else:
                                await safe_sleep(fe.seconds + 2)
                                try:
                                    await client.kick_participant(entity, u)
                                    exp_count += 1
                                    print(f"      [{i}/{len(to_remove)}] Expulsado tras espera: {uname}")
                                except Exception:
                                    pass
                        except Exception as e:
                            print(f"      ❌ Error con {uname}: {e}")

                    info_bunker["expulsados"] = exp_count
                    if not skip_channel:
                        info_bunker["pendientes"] = len(to_remove) - exp_count

                    # Recuento final
                    final_parts = await client.get_participants(entity, limit=100)
                    info_bunker["total_restantes"] = len(final_parts)
                else:
                    print("   ⚠️ Saltando expulsiones: falta permiso de ban.")
                    info_bunker["pendientes"] = "Falta permiso ban"

            except Exception as e:
                print(f"   ❌ Error accediendo al búnker {b_id}: {e}")

            resumen_final.append(info_bunker)
            await safe_sleep(1.0)

        print("\n" + "=" * 80)
        print("RESUMEN DE BLINDAJE Y LIMPIEZA DE BÚNKERS")
        print("=" * 80)
        for r in resumen_final:
            print(f"- {r['nombre']}:")
            print(f"    Enlace privado: {r['enlace_nuevo']}")
            print(f"    Sin restricciones (noforwards): {'✅' if r['noforwards_ok'] else '⚠️'}")
            print(f"    Expulsados: {r['expulsados']} | Pendientes: {r['pendientes']} | Miembros actuales: {r['total_restantes']}")

if __name__ == "__main__":
    asyncio.run(main())
