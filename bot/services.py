"""Bot va Mini App uchun umumiy biznes-mantiq (zayavka yaratish, qaror, bildirishnomalar)."""
from aiogram import Bot

from . import db
from .keyboards import decision_kb
from .notify import notify
from .render import render_card


async def after_create(bot: Bot, rid: int, author_id: int) -> None:
    await db.add_history(rid, author_id, "created")
    req = await db.get_request(rid)
    fields = await db.list_fields()
    approvers = [i for i in await db.user_ids_by_roles(["approver", "admin"]) if i != author_id]
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
