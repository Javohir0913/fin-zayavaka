"""Bot va Mini App uchun umumiy biznes-mantiq.

Har bir o'zgartiruvchi amal shu yerdan o'tadi — shuning uchun audit log (kim, qachon, oldin -> keyin)
bitta joyda yoziladi va bot ham, ilova ham bir xil ishlaydi.
"""
from aiogram import Bot

from . import audit, db, rates
from .keyboards import decision_kb, main_menu, role_assign_kb
from .notify import notify
from .render import render_card
from .utils import FIELD_TYPES, ROLES, allowed_roles, e, fmt_amount, fmt_date

STATUS_TXT = {"pending": "Kutilmoqda", "approved": "Tasdiqlangan", "rejected": "Rad etilgan", "cancelled": "Bekor qilingan"}


def _req_label(req: dict) -> str:
    return f"#{req['id']} {req['title'][:60]}"


# ---------------------------------------------------------------- foydalanuvchilar
async def notify_new_user(bot: Bot, uid: int, full_name: str, username: str | None) -> None:
    """Yangi foydalanuvchi haqida: super adminga barcha rollar, adminlarga — admin rolisiz."""
    uname = f" @{e(username)}" if username else ""
    text = f"🆕 <b>Yangi foydalanuvchi</b>\n{e(full_name)}{uname}\nID: <code>{uid}</code>\n\nRol tanlang:"
    supers = await db.user_ids_by_roles(["superadmin"])
    admins = await db.user_ids_by_roles(["admin"])
    await notify(bot, supers, text, role_assign_kb(uid, allowed_roles({"role": "superadmin"})))
    await notify(bot, admins, text, role_assign_kb(uid, allowed_roles({"role": "admin"})))


async def set_role(bot: Bot, actor: dict, target: dict, role: str) -> bool:
    """Ruxsat tekshiruvi chaqiruvchida (utils.role_change_error). True — o'zgardi."""
    old = target["role"]
    if old == role:
        return False
    await db.set_role(target["id"], role)
    await audit.write(actor, "user", target["id"], "role_changed", "role", ROLES.get(old, old), ROLES.get(role, role),
                      label=target["full_name"])
    target = {**target, "role": role}
    try:
        if role == "blocked":
            await bot.send_message(target["id"], "⛔ Sizning kirishingiz bloklandi.")
        else:
            await bot.send_message(target["id"], f"🎉 Sizga rol berildi: <b>{ROLES[role]}</b>\n\n/start — menyuni ochish",
                                   reply_markup=main_menu(target))
    except Exception:
        pass
    return True


# ---------------------------------------------------------------- zayavkalar
async def create_request(bot: Bot, actor: dict, title: str, amount: float, currency: str,
                         needed_date: str, comment: str, extra: dict) -> int:
    await rates.ensure_today()  # zayavka kunining kursi bazada bo'lsin
    rid = await db.create_request(actor["id"], title, amount, currency, needed_date, comment, extra)
    await db.add_history(rid, actor["id"], "created")
    await audit.write(actor, "request", rid, "created", "", None,
                      f"{fmt_amount(amount)} {currency} · {fmt_date(needed_date)} · {title}", label=f"#{rid} {title[:60]}")
    req = await db.get_request(rid)
    fields = await db.list_fields()
    approvers = [i for i in await db.user_ids_by_roles(["approver", "admin", "superadmin"]) if i != actor["id"]]
    await notify(bot, approvers, "🆕 <b>Yangi zayavka!</b>\n\n" + render_card(req, fields), decision_kb(rid))
    return rid


async def edit_request(bot: Bot, actor: dict, req: dict, upd: dict, changes: list[tuple[str, object, object]]) -> None:
    """upd — bazaga yoziladigan ustunlar; changes — [(maydon nomi, eski, yangi)] odam o'qiydigan ko'rinishda."""
    if not upd:
        return
    await db.update_request(req["id"], **upd)
    details = "; ".join(f"{f}: {o if o not in (None, '') else '—'} → {n if n not in (None, '') else '—'}" for f, o, n in changes)
    await db.add_history(req["id"], actor["id"], "edited", details[:1000])
    await audit.write_changes(actor, "request", req["id"], changes, label=_req_label(req))
    if req["user_id"] != actor["id"]:
        await notify(bot, [req["user_id"]], f"✏️ Zayavkangiz <b>#{req['id']}</b> tahrirlandi:\n{e(details)}\n\nKo'rish: /r{req['id']}")


async def _status_change(actor: dict, rid: int, old_status: str, new_status: str, action: str, reason: str = "") -> None:
    await db.add_history(rid, actor["id"], action, reason)
    req = await db.get_request(rid)
    await audit.write(actor, "request", rid, action, "status", STATUS_TXT[old_status], STATUS_TXT[new_status],
                      label=_req_label(req))
    if reason:
        await audit.write(actor, "request", rid, action, "reject_reason", None, reason, label=_req_label(req))


async def approve(bot: Bot, rid: int, actor: dict) -> bool:
    if not await db.decide(rid, "approved", actor["id"]):
        return False
    await _status_change(actor, rid, "pending", "approved", "approved")
    req = await db.get_request(rid)
    if req["user_id"] != actor["id"]:
        fields = await db.list_fields()
        await notify(bot, [req["user_id"]], f"✅ Zayavkangiz <b>#{rid}</b> tasdiqlandi!\n\n" + render_card(req, fields))
    return True


async def reject(bot: Bot, rid: int, actor: dict, reason: str) -> bool:
    if not await db.decide(rid, "rejected", actor["id"], reason):
        return False
    await _status_change(actor, rid, "pending", "rejected", "rejected", reason)
    req = await db.get_request(rid)
    if req["user_id"] != actor["id"]:
        fields = await db.list_fields()
        await notify(bot, [req["user_id"]], f"❌ Zayavkangiz <b>#{rid}</b> rad etildi.\n\n" + render_card(req, fields))
    return True


async def cancel(rid: int, actor: dict) -> bool:
    if not await db.decide(rid, "cancelled", actor["id"]):
        return False
    await _status_change(actor, rid, "pending", "cancelled", "cancelled")
    return True


async def reopen(bot: Bot, rid: int, actor: dict) -> bool:
    before = await db.get_request(rid)
    if not before or not await db.reopen(rid):
        return False
    await _status_change(actor, rid, before["status"], "pending", "reopened")
    if before["user_id"] != actor["id"]:
        await notify(bot, [before["user_id"]], f"↩️ Zayavkangiz <b>#{rid}</b> qayta ko'rib chiqishga qaytarildi.")
    return True


# ---------------------------------------------------------------- qo'shimcha maydonlar
_FIELD_LABELS = {"name": "Nomi", "required": "Majburiy", "active": "Faol", "options": "Variantlar"}


def _field_val(k: str, v):
    if k in ("required", "active"):
        return bool(v)
    if k == "options":
        return ", ".join(v)
    return v


async def add_field(actor: dict, name: str, ftype: str, options: list[str], required: bool) -> int:
    fid = await db.add_field(name, ftype, options, required)
    await audit.write(actor, "field", fid, "created", "", None,
                      f"{name} · {FIELD_TYPES[ftype]}" + (f" · {', '.join(options)}" if options else "")
                      + (" · majburiy" if required else ""), label=name)
    return fid


async def update_field(actor: dict, field: dict, **upd) -> None:
    changes = [(_FIELD_LABELS[k], _field_val(k, field[k]), _field_val(k, v)) for k, v in upd.items() if field[k] != v]
    if not changes:
        return
    await db.update_field(field["id"], **upd)
    await audit.write_changes(actor, "field", field["id"], changes, label=upd.get("name", field["name"]))


async def move_field_up(actor: dict, field: dict) -> None:
    before = [f["id"] for f in await db.list_fields()]
    await db.move_field_up(field["id"])
    after = [f["id"] for f in await db.list_fields()]
    if before != after:
        await audit.write(actor, "field", field["id"], "moved", "Tartib", before.index(field["id"]) + 1,
                          after.index(field["id"]) + 1, label=field["name"])


async def delete_field(actor: dict, field: dict) -> None:
    await db.delete_field(field["id"])
    await audit.write(actor, "field", field["id"], "deleted", "",
                      f"{field['name']} · {FIELD_TYPES.get(field['type'], field['type'])}"
                      + (f" · {', '.join(field['options'])}" if field.get("options") else ""), None, label=field["name"])


# ---------------------------------------------------------------- valyutalar
async def add_currency(actor: dict, code: str) -> None:
    before = {c["code"]: c for c in await db.list_currencies(active_only=False)}
    await db.add_currency(code)
    await rates.ensure_today()  # yangi valyutaning bugungi kursi
    if code not in before:
        await audit.write(actor, "currency", code, "created", "", None, code, label=code)
    elif not before[code]["active"]:
        await audit.write(actor, "currency", code, "edited", "Faol", False, True, label=code)


async def toggle_currency(actor: dict, code: str) -> None:
    cur = next((c for c in await db.list_currencies(active_only=False) if c["code"] == code), None)
    if not cur:
        return
    await db.toggle_currency(code)
    await audit.write(actor, "currency", code, "edited", "Faol", bool(cur["active"]), not cur["active"], label=code)
