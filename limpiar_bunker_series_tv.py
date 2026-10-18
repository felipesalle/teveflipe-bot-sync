import asyncio
import os
import random
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetParticipantRequest, EditBannedRequest
from telethon.tl.functions.messages import (
    ToggleNoForwardsRequest,
    ExportChatInviteRequest,
    GetExportedChatInvitesRequest,
    EditExportedChatInviteRequest
)
from telethon.tl.types import ChatBannedRights

API_ID = int(os.getenv("TELEGRAM_API_ID", "28045969"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "d8e515c5687943e5e0bf046f87c3d2cc")
SESSION_PROD = os.getenv("SESSION_PROD", "")

BUNKER_SERIES = -1002097175258
SAFE_USER_IDS = {
    6740086,     # Flipe loflipa (Propietario / Felipe)
    7192044593,    # TeVeflipe (Bot / Sesión)
}

async def safe_sleep(secs: float):
    await asyncio.sleep(secs)

async def main():
    async with TelegramClient(StringSession(SESSION_PROD), API_ID, API_HASH) as client:
        me = await client.get_me()
        print(f"Cuenta autenticada: {me.first_name} (ID: {me.id})")
        SAFE_USER_IDS.add(me.id)

        entity = await client.get_entity(BUNKER_SERIES)
        print(f"\n🎯 Conectado al Búnker: {entity.title} (ID: {entity.id})")

        # 1. Verificar permisos de Administrador
        try:
            p = await client(GetParticipantRequest(channel=entity, participant=me))
            p_type = type(p.participant).__name__
            rights = getattr(p.participant, "admin_rights", None)
            can_ban = getattr(rights, "ban_users", False) if rights else (p_type == "ChannelParticipantCreator")
            print(f"   Rol: {p_type}")
            print(f"   Permiso ban_users: {can_ban}")
            if not can_ban and p_type != "ChannelParticipantCreator":
                print("❌ ERROR: La cuenta aún no tiene permisos para eliminar usuarios (ban_users=False).")
                return
        except Exception as e:
            print(f"⚠️ Error verificando rol: {e}")
            return

        # 2. Desactivar 'noforwards' en el Búnker
        print("\n🔓 Desactivando 'Restringir guardar contenido' (noforwards) en Búnker...")
        try:
            await client(ToggleNoForwardsRequest(peer=entity, enabled=False))
            print("✅ 'Restringir guardar contenido' desactivado correctamente en el Búnker.")
        except Exception as e:
            print(f"ℹ️ noforwards: {e}")

        # 3. Revocar enlaces de invitación antiguos
        print("\n🔗 Revocando enlaces de invitación anteriores...")
        try:
            # Crear un nuevo enlace primario revocando el anterior
            new_invite = await client(ExportChatInviteRequest(peer=entity))
            print(f"✅ Nuevo enlace generado (solo para tu uso): {getattr(new_invite, 'link', 'creado')}")

            # Revocar enlaces adicionales si existieran
            try:
                invites = await client(GetExportedChatInvitesRequest(peer=entity, admin_id=me, limit=50))
                for inv in getattr(invites, "invites", []):
                    if not inv.revoked and inv.link != getattr(new_invite, "link", None):
                        try:
                            await client(EditExportedChatInviteRequest(peer=entity, link=inv.link, revoked=True))
                            print(f"   🔒 Enlace secundario revocado: {inv.link}")
                        except Exception:
                            pass
            except Exception as e:
                print(f"ℹ️ Chequeo de enlaces secundarios: {e}")
        except Exception as e:
            print(f"⚠️ Aviso revocando enlaces: {e}")

        # 4. Obtener participantes ajenos
        print("\n👥 Analizando participantes del Búnker...")
        participants = await client.get_participants(entity, limit=500)
        total_p = len(participants)
        print(f"Total miembros encontrados: {total_p}")

        to_remove = []
        for u in participants:
            if u.id in SAFE_USER_IDS or u.bot:
                continue
            to_remove.append(u)

        print(f"Miembros a mantener seguros (Tú y bots): {total_p - len(to_remove)}")
        print(f"Miembros ajenos a expulsar: {len(to_remove)}")

        if not to_remove:
            print("🎉 ¡No hay usuarios ajenos en este Búnker! Ya está 100% limpio.")
            return

        # 5. Expulsar usuarios ajenos
        print(f"\n🚪 Expulsando a los {len(to_remove)} usuarios ajenos...")
        expulsados = 0
        errores = 0

        for i, u in enumerate(to_remove, start=1):
            name = f"{u.first_name or ''} {u.last_name or ''}".strip() or f"Usuario_{u.id}"
            try:
                # kick_participant: lo expulsa del canal
                await client.kick_participant(entity, u)
                expulsados += 1
                print(f"   [{i}/{len(to_remove)}] ✅ Expulsado: {name} (ID: {u.id})", flush=True)
                await safe_sleep(0.5)
            except errors.FloodWaitError as fe:
                print(f"   ⏳ FloodWait: esperando {fe.seconds}s...", flush=True)
                await safe_sleep(fe.seconds + 2)
                try:
                    await client.kick_participant(entity, u)
                    expulsados += 1
                    print(f"   [{i}/{len(to_remove)}] ✅ Expulsado tras espera: {name}", flush=True)
                except Exception as e2:
                    errores += 1
                    print(f"   [{i}/{len(to_remove)}] ❌ Error con {name}: {e2}", flush=True)
            except Exception as e:
                errores += 1
                print(f"   [{i}/{len(to_remove)}] ❌ Error con {name}: {e}", flush=True)

        print(f"\n📊 RESUMEN: {expulsados} expulsados correctamente, {errores} errores.")

        # 6. Verificación final de miembros restantes
        remaining = await client.get_participants(entity, limit=100)
        print(f"\n👥 Miembros restantes en el Búnker ({len(remaining)}):")
        for r in remaining:
            rname = f"{r.first_name or ''} {r.last_name or ''}".strip()
            status = "[TÚ]" if r.id == 6740086 else ("[BOT]" if r.bot else "[USUARIO]")
            print(f"   - {status} {rname} (ID: {r.id})")

        print("\n🎉 ¡BÚNKER 'SERIES TV' BLINDADO Y LIMPIO AL 100%!")

if __name__ == "__main__":
    asyncio.run(main())
