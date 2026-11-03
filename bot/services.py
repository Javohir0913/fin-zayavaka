"""Bot va Mini App uchun umumiy biznes-mantiq (zayavka yaratish, qaror, bildirishnomalar)."""
from aiogram import Bot

from . import db
from .keyboards import decision_kb, role_assign_kb
from .notify import notify
from .render import render_card
from .utils import allowed_roles, e


async def notify_new_user(bot: Bot, uid: int, full_name: str, username: str | None) -> None:
    """Yangi foydalanuvchi haqida: super adminlarga barcha rollar, adminlarga — admin rolisiz."""
    uname = f" @{e(username)}" if username else ""
    text = f"🆕 <b>Yangi foydalanuvchi</b>\n{e(full_name)}{uname}\nID: <code>{uid}</code>\n\nRol tanlang:"
    supers = await db.user_ids_by_roles(["superadmin"])
    admins = await db.user_ids_by_roles(["admin"])
    await notify(bot, supers, text, role_assign_kb(uid, allowed_roles({"role": "superadmin"})))
    await notify(bot, admins, text, role_assign_kb(uid, allowed_roles({"role": "admin"})))


async def after_create(bot: Bot, rid: int, author_id: int) -> None:
    await db.add_history(rid, author_id, "created")
    req = await db.get_request(rid)
    fields = await db.list_fields()
    approvers = [i for i in await db.user_ids_by_roles(["approver", "admin", "superadmin"]) if i != author_id]
    await notify(bot, approvers, "🆕 <b>Yangi zayavka!</b>\n\n" + render_card(req, fields), decision_kb(rid))


async def approve(bot: Bot, rid: int, by: int) -> bool:
    if not await db.decide(rid, "approved", by):
        return False
    await db.add_history(rid, by, "approved")
    req = await db.get_request(rid)
    if req["user_id"] != by:
        fields = await db.list_fields()
        await notify(bot, [req["user_id"]], f"✅ Zayavkangiz <b>#{rid}</b> tasdiqlandi!\n\n" + render_card(req, fields))
    return True


async def reject(bot: Bot, rid: int, by: int, reason: str) -> bool:
    if not await db.decide(rid, "rejected", by, reason):
        return False
    await db.add_history(rid, by, "rejected", reason)
    req = await db.get_request(rid)
    if req["user_id"] != by:
        fields = await db.list_fields()
        await notify(bot, [req["user_id"]], f"❌ Zayavkangiz <b>#{rid}</b> rad etildi.\n\n" + render_card(req, fields))
    return True


async def cancel(rid: int, by: int) -> bool:
    if not await db.decide(rid, "cancelled", by):
        return False
    await db.add_history(rid, by, "cancelled")
    return True


async def reopen(bot: Bot, rid: int, by: int) -> bool:
    if not await db.reopen(rid):
        return False
    await db.add_history(rid, by, "reopened")
    req = await db.get_request(rid)
    if req["user_id"] != by:
        await notify(bot, [req["user_id"]], f"↩️ Zayavkangiz <b>#{rid}</b> qayta ko'rib chiqishga qaytarildi.")
    return True
