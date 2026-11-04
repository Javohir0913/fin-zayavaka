"""Zayavkalarni ko'rish, tahrirlash, tasdiqlash / rad etish, tarix, muddatlar."""
from datetime import date, timedelta

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import db, services
from ..config import PAGE_SIZE
from ..fieldinput import ask_field, parse_field_callback, parse_field_message
from ..keyboards import (BTN_ALL, BTN_DUE, BTN_MY, BTN_PENDING, abort_row, btn, card_kb,
                         currency_kb, date_kb, ikb, list_kb)
from ..render import fmt_field_value, render_card, text_line
from ..states import EditReq, RejectReq
from ..utils import (HISTORY_ACTIONS, STATUS, can, e, fmt_amount, fmt_date, fmt_dt, parse_amount,
                     parse_date, today)

router = Router(name="view")

BUILTIN = {
    "title": ("🎯 Maqsad", "title"),
    "amount": ("💰 Summa", "amount"),
    "currency": ("💱 Valyuta", "currency"),
    "date": ("📅 Kerakli sana", "needed_date"),
    "comment": ("💬 Izoh", "comment"),
}


# ---------------------------------------------------------------- yordamchilar
def _can_view(user: dict, req: dict) -> bool:
    return req["user_id"] == user["id"] or can(user, "view_all")


def _can_edit(user: dict, req: dict) -> bool:
    return can(user, "admin") or (req["user_id"] == user["id"] and req["status"] == "pending")


async def _load(cb_or_msg, user: dict, rid: int) -> dict | None:
    req = await db.get_request(rid)
    err = None
    if not req:
        err = "Zayavka topilmadi"
    elif not _can_view(user, req):
        err = "Bu zayavkani ko'rishga ruxsatingiz yo'q"
    if err:
        if isinstance(cb_or_msg, CallbackQuery):
            await cb_or_msg.answer(err, show_alert=True)
        else:
            await cb_or_msg.answer(err)
        return None
    return req


def _has_files(req: dict, fields: list[dict]) -> bool:
    return any(f["type"] == "file" and str(f["id"]) in req["extra"] for f in fields)


async def card_payload(req: dict, user: dict):
    fields = await db.list_fields()
    return render_card(req, fields), card_kb(req, user, _has_files(req, fields))


async def send_card(msg: Message, req: dict, user: dict):
    text, kb = await card_payload(req, user)
    await msg.answer(text, reply_markup=kb)


async def edit_card(msg: Message, req: dict, user: dict):
    text, kb = await card_payload(req, user)
    try:
        await msg.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:  # "message is not modified" yoki xabar juda eski
        pass


# ---------------------------------------------------------------- ro'yxatlar
async def _list_text_kb(user: dict, scope: str, status: str, page: int):
    uid = user["id"] if scope == "my" else None
    total = await db.count_requests(uid, status)
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(max(page, 0), pages - 1)
    items = await db.list_requests(uid, status, page * PAGE_SIZE, PAGE_SIZE)
    title = "📋 <b>Mening zayavkalarim</b>" if scope == "my" else "📂 <b>Barcha zayavkalar</b>"
    flt = "Hammasi" if status == "all" else STATUS[status]
    text = f"{title}\nFiltr: {flt} · Jami: {total}"
    if not items:
        text += "\n\nHozircha zayavka yo'q."
    else:
        text += "\n\nKo'rish uchun zayavkani tanlang 👇"
    return text, list_kb(items, scope, status, page, total, PAGE_SIZE)


@router.message(F.text == BTN_MY)
async def my_list(message: Message, state: FSMContext, user: dict):
    await state.clear()
    text, kb = await _list_text_kb(user, "my", "all", 0)
    await message.answer(text, reply_markup=kb)


@router.message(F.text == BTN_ALL)
async def all_list(message: Message, state: FSMContext, user: dict):
    await state.clear()
    if not can(user, "view_all"):
        return
    text, kb = await _list_text_kb(user, "all", "all", 0)
    await message.answer(text, reply_markup=kb)


@router.message(F.text == BTN_PENDING)
async def pending_list(message: Message, state: FSMContext, user: dict):
    await state.clear()
    if not can(user, "view_all"):
        return
    text, kb = await _list_text_kb(user, "all", "pending", 0)
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("ls:"))
async def list_cb(cb: CallbackQuery, user: dict):
    _, scope, status, page = cb.data.split(":")
    if scope == "all" and not can(user, "view_all"):
        await cb.answer("Ruxsat yo'q", show_alert=True)
        return
    text, kb = await _list_text_kb(user, scope, status, int(page))
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        pass
    await cb.answer()


# ---------------------------------------------------------------- kartochka
@router.message(F.text.regexp(r"^/r(\d+)(@\w+)?$").as_("m"))
async def open_by_command(message: Message, state: FSMContext, user: dict, m):
    await state.clear()
    req = await _load(message, user, int(m.group(1)))
    if req:
        await send_card(message, req, user)


@router.callback_query(F.data.startswith("rq:v:"))
async def view_card(cb: CallbackQuery, user: dict):
    req = await _load(cb, user, int(cb.data.split(":")[2]))
    if req:
        await send_card(cb.message, req, user)
        await cb.answer()


@router.callback_query(F.data.startswith("rq:rf:"))
async def refresh_card(cb: CallbackQuery, user: dict, state: FSMContext):
    await state.clear()
    req = await _load(cb, user, int(cb.data.split(":")[2]))
    if req:
        await edit_card(cb.message, req, user)
        await cb.answer()


@router.callback_query(F.data.startswith("rq:h:"))
async def history(cb: CallbackQuery, user: dict):
    req = await _load(cb, user, int(cb.data.split(":")[2]))
    if not req:
        return
    rows = await db.get_history(req["id"])
    lines = [f"🕓 <b>Zayavka #{req['id']} tarixi</b>", ""]
    for h in rows:
        line = f"{fmt_dt(h['created_at'])} — {HISTORY_ACTIONS.get(h['action'], h['action'])} · {e(h['full_name'] or '—')}"
        if h["details"]:
            line += f"\n    <i>{e(h['details'])}</i>"
        lines.append(line)
    text = "\n".join(lines)
    await cb.message.answer(text[:4000])
    await cb.answer()


@router.callback_query(F.data.startswith("rq:f:"))
async def files(cb: CallbackQuery, user: dict, bot: Bot):
    req = await _load(cb, user, int(cb.data.split(":")[2]))
    if not req:
        return
    await cb.answer()
    for f in await db.list_fields():
        v = req["extra"].get(str(f["id"]))
        if f["type"] != "file" or not isinstance(v, dict):
            continue
        caption = f"#{req['id']} · {e(f['name'])}"
        try:
            if v.get("kind") == "photo":
                await bot.send_photo(cb.message.chat.id, v["file_id"], caption=caption)
            else:
                await bot.send_document(cb.message.chat.id, v["file_id"], caption=caption)
        except TelegramBadRequest:
            await cb.message.answer(f"{caption}: faylni yuborib bo'lmadi")


# ---------------------------------------------------------------- qaror
@router.callback_query(F.data.startswith("rq:ap:"))
async def approve(cb: CallbackQuery, user: dict, bot: Bot):
    if not can(user, "decide"):
        await cb.answer("Ruxsat yo'q", show_alert=True)
        return
    rid = int(cb.data.split(":")[2])
    if not await services.approve(bot, rid, user):
        await cb.answer("Bu zayavka allaqachon ko'rib chiqilgan", show_alert=True)
    else:
        await cb.answer("✅ Tasdiqlandi")
    req = await db.get_request(rid)
    if req:
        await edit_card(cb.message, req, user)


@router.callback_query(F.data.startswith("rq:rj:"))
async def reject_start(cb: CallbackQuery, user: dict, state: FSMContext):
    if not can(user, "decide"):
        await cb.answer("Ruxsat yo'q", show_alert=True)
        return
    rid = int(cb.data.split(":")[2])
    req = await db.get_request(rid)
    if not req or req["status"] != "pending":
        await cb.answer("Bu zayavka allaqachon ko'rib chiqilgan", show_alert=True)
        if req:
            await edit_card(cb.message, req, user)  # eskirgan tugmalarni olib tashlaymiz
        return
    await state.set_state(RejectReq.reason)
    await state.update_data(req_id=rid)
    await cb.answer()
    await cb.message.answer(
        f"❌ Zayavka <b>#{rid}</b> ({fmt_amount(req['amount'])} {req['currency']}) — rad etish sababini yozing:",
        reply_markup=ikb([[btn("Sababsiz rad etish", "rjs")], abort_row()]),
    )


@router.message(RejectReq.reason, F.text)
async def reject_reason(message: Message, state: FSMContext, user: dict, bot: Bot):
    await _do_reject(message, state, user, bot, message.text.strip()[:500])


@router.callback_query(RejectReq.reason, F.data == "rjs")
async def reject_no_reason(cb: CallbackQuery, state: FSMContext, user: dict, bot: Bot):
    await cb.answer()
    await cb.message.edit_reply_markup(reply_markup=None)
    await _do_reject(cb.message, state, user, bot, "")


async def _do_reject(msg: Message, state: FSMContext, user: dict, bot: Bot, reason: str):
    rid = (await state.get_data()).get("req_id")
    await state.clear()
    if not rid or not can(user, "decide") or not await services.reject(bot, rid, user, reason):
        await msg.answer("Bu zayavka allaqachon ko'rib chiqilgan.")
        return
    await send_card(msg, await db.get_request(rid), user)


@router.callback_query(F.data.startswith("rq:cn:"))
async def cancel_req(cb: CallbackQuery, user: dict):
    rid = int(cb.data.split(":")[2])
    req = await db.get_request(rid)
    if not req or req["user_id"] != user["id"]:
        await cb.answer("Faqat muallif bekor qila oladi", show_alert=True)
        return
    if req["status"] != "pending":
        await cb.answer("Faqat kutilayotgan zayavkani bekor qilish mumkin", show_alert=True)
        return
    await cb.message.edit_reply_markup(reply_markup=ikb([
        [btn("🚫 Ha, bekor qilinsin", f"rq:cny:{rid}"), btn("⬅️ Yo'q", f"rq:rf:{rid}")],
    ]))
    await cb.answer()


@router.callback_query(F.data.startswith("rq:cny:"))
async def cancel_req_yes(cb: CallbackQuery, user: dict, bot: Bot):
    rid = int(cb.data.split(":")[2])
    req = await db.get_request(rid)
    if not req or req["user_id"] != user["id"] or not await services.cancel(bot, rid, user):
        await cb.answer("Bekor qilib bo'lmadi", show_alert=True)
        return
    await cb.answer("Bekor qilindi")
    await edit_card(cb.message, await db.get_request(rid), user)


@router.callback_query(F.data.startswith("rq:rp:"))
async def reopen(cb: CallbackQuery, user: dict, bot: Bot):
    if not can(user, "admin"):
        await cb.answer("Ruxsat yo'q", show_alert=True)
        return
    rid = int(cb.data.split(":")[2])
    if await services.reopen(bot, rid, user):
        await cb.answer("↩️ Kutishga qaytarildi")
    else:
        await cb.answer()
    req = await db.get_request(rid)
    if req:
        await edit_card(cb.message, req, user)


# ---------------------------------------------------------------- tahrirlash
@router.callback_query(F.data.startswith("rq:ed:"))
async def edit_menu(cb: CallbackQuery, user: dict, state: FSMContext):
    await state.clear()
    rid = int(cb.data.split(":")[2])
    req = await _load(cb, user, rid)
    if not req:
        return
    if not _can_edit(user, req):
        await cb.answer("Tahrirlab bo'lmaydi: faqat kutilayotgan zayavkani muallif tahrirlaydi", show_alert=True)
        return
    rows = [[btn(label, f"re:{rid}:{key}")] for key, (label, _) in BUILTIN.items()]
    for f in await db.list_fields(active_only=True):
        rows.append([btn(f"🧩 {f['name']}", f"re:{rid}:f{f['id']}")])
    rows.append([btn("⬅️ Orqaga", f"rq:rf:{rid}")])
    await cb.message.edit_reply_markup(reply_markup=ikb(rows))
    await cb.answer("Nimani o'zgartirasiz?")


@router.callback_query(F.data.startswith("re:"))
async def edit_attr(cb: CallbackQuery, user: dict, state: FSMContext):
    _, rid, attr = cb.data.split(":")
    rid = int(rid)
    req = await _load(cb, user, rid)
    if not req:
        return
    if not _can_edit(user, req):
        await cb.answer("Tahrirlab bo'lmaydi", show_alert=True)
        return
    await state.set_state(EditReq.value)
    await state.update_data(req_id=rid, attr=attr)
    await cb.answer()
    msg = cb.message
    abort = ikb([abort_row()])
    if attr == "title":
        await msg.answer(f"Hozirgi maqsad: <i>{e(req['title'])}</i>\n\nYangi maqsadni yozing:", reply_markup=abort)
    elif attr == "amount":
        await msg.answer(f"Hozirgi summa: <b>{fmt_amount(req['amount'])} {req['currency']}</b>\n\nYangi summani kiriting:",
                         reply_markup=abort)
    elif attr == "currency":
        await msg.answer(f"Hozirgi valyuta: <b>{req['currency']}</b>\n\nYangisini tanlang:",
                         reply_markup=currency_kb(await db.list_currencies(), "ec", with_abort=True))
    elif attr == "date":
        await msg.answer(f"Hozirgi sana: <b>{fmt_date(req['needed_date'])}</b>\n\nYangi sanani tanlang yoki yozing (KK.OO.YYYY):",
                         reply_markup=date_kb("ed", with_abort=True))
    elif attr == "comment":
        await msg.answer(f"Hozirgi izoh: <i>{e(req['comment']) or '—'}</i>\n\nYangi izohni yozing:",
                         reply_markup=ikb([[btn("🧹 Izohni o'chirish", "ecl")], abort_row()]))
    elif attr.startswith("f"):
        field = await db.get_field(int(attr[1:]))
        if not field:
            await state.clear()
            await msg.answer("Maydon topilmadi.")
            return
        cur = req["extra"].get(str(field["id"]))
        await msg.answer(f"Hozirgi qiymat: {fmt_field_value(field, cur)}")
        await ask_field(msg, field, "efv", editing=True)


async def _apply_edit(msg: Message, state: FSMContext, user: dict, bot: Bot, value):
    data = await state.get_data()
    await state.clear()
    rid, attr = data.get("req_id"), data.get("attr")
    req = await db.get_request(rid) if rid else None
    if not req or not _can_edit(user, req):
        await msg.answer("Tahrirlab bo'lmaydi (zayavka holati o'zgargan bo'lishi mumkin).")
        return
    if attr in BUILTIN:
        label, col = BUILTIN[attr]
        label = label.split(" ", 1)[1]  # emojisiz: "Summa", "Maqsad" ...
        old = req[col]
        if old == value:
            await msg.answer("O'zgarish yo'q.")
            return
        upd = {col: value}
        if attr == "amount":
            old, value = fmt_amount(old), fmt_amount(value)
        elif attr == "date":
            old, value = fmt_date(old), fmt_date(value)
    else:
        field = await db.get_field(int(attr[1:]))
        if not field:
            await msg.answer("Maydon topilmadi.")
            return
        label = field["name"]
        extra = dict(req["extra"])
        old = fmt_field_value(field, extra.get(str(field["id"])))
        if value is None:
            extra.pop(str(field["id"]), None)
        else:
            extra[str(field["id"])] = value
        upd = {"extra": extra}
        value = fmt_field_value(field, value)
    await services.edit_request(bot, user, req, upd, [(label, old, value)])
    await msg.answer("✏️ Saqlandi.")
    await send_card(msg, await db.get_request(rid), user)


@router.message(EditReq.value)
async def edit_value_msg(message: Message, state: FSMContext, user: dict, bot: Bot):
    attr = (await state.get_data()).get("attr", "")
    text = (message.text or "").strip()
    if attr == "title":
        if not 3 <= len(text) <= 500:
            await message.answer("Maqsad 3 dan 500 belgigacha bo'lishi kerak.")
            return
        await _apply_edit(message, state, user, bot, text)
    elif attr == "amount":
        v = parse_amount(text)
        if v is None:
            await message.answer("❗ Summa noto'g'ri.")
            return
        await _apply_edit(message, state, user, bot, v)
    elif attr == "date":
        d = parse_date(text)
        if not d:
            await message.answer("❗ Sana noto'g'ri. Masalan: <code>15.11.2026</code>")
            return
        await _apply_edit(message, state, user, bot, d.isoformat())
    elif attr == "comment":
        if not text or len(text) > 1000:
            await message.answer("Izoh 1–1000 belgi bo'lishi kerak.")
            return
        await _apply_edit(message, state, user, bot, text)
    elif attr == "currency":
        await message.answer("Iltimos, tugmalardan valyutani tanlang.")
    elif attr.startswith("f"):
        field = await db.get_field(int(attr[1:]))
        if not field:
            await state.clear()
            return
        ok, value = parse_field_message(field, message)
        if not ok:
            await message.answer(f"❗ {value}")
            return
        await _apply_edit(message, state, user, bot, value)


@router.callback_query(EditReq.value, F.data.startswith("ec:"))
async def edit_currency(cb: CallbackQuery, state: FSMContext, user: dict, bot: Bot):
    await cb.answer()
    await cb.message.edit_reply_markup(reply_markup=None)
    await _apply_edit(cb.message, state, user, bot, cb.data.split(":", 1)[1])


@router.callback_query(EditReq.value, F.data.startswith("ed:"))
async def edit_date(cb: CallbackQuery, state: FSMContext, user: dict, bot: Bot):
    await cb.answer()
    await cb.message.edit_reply_markup(reply_markup=None)
    await _apply_edit(cb.message, state, user, bot, cb.data.split(":", 1)[1])


@router.callback_query(EditReq.value, F.data == "ecl")
async def edit_clear_comment(cb: CallbackQuery, state: FSMContext, user: dict, bot: Bot):
    await cb.answer()
    await cb.message.edit_reply_markup(reply_markup=None)
    await _apply_edit(cb.message, state, user, bot, "")


@router.callback_query(EditReq.value, F.data.startswith("efv:"))
async def edit_field_cb(cb: CallbackQuery, state: FSMContext, user: dict, bot: Bot):
    attr = (await state.get_data()).get("attr", "")
    field = await db.get_field(int(attr[1:])) if attr.startswith("f") else None
    if not field:
        await cb.answer("Maydon topilmadi", show_alert=True)
        return
    ok, value = parse_field_callback(field, cb.data)
    if not ok:
        await cb.answer(str(value), show_alert=True)
        return
    await cb.answer()
    await cb.message.edit_reply_markup(reply_markup=None)
    await _apply_edit(cb.message, state, user, bot, value)


# ---------------------------------------------------------------- muddatlar
@router.message(F.text == BTN_DUE)
async def due_dates(message: Message, state: FSMContext, user: dict):
    await state.clear()
    uid = None if can(user, "view_all") else user["id"]
    t = today()
    overdue = await db.overdue_pending(t.isoformat(), uid)
    upcoming = await db.requests_due_between(t.isoformat(), (t + timedelta(days=14)).isoformat(), uid)
    with_author = uid is None
    lines = ["📅 <b>Muddatlar</b> (keyingi 14 kun)", ""]
    if overdue:
        lines.append(f"⚠️ <b>Muddati o'tgan, hali kutilmoqda: {len(overdue)}</b>")
        lines += [f"  {fmt_date(r['needed_date'])} · {text_line(r, with_author)}" for r in overdue[:15]]
        lines.append("")
    if not upcoming:
        lines.append("Yaqin kunlarda kerak bo'ladigan zayavka yo'q.")
    by_day: dict[str, list] = {}
    for r in upcoming:
        by_day.setdefault(r["needed_date"], []).append(r)
    for day, items in by_day.items():
        d = date.fromisoformat(day)
        delta = (d - t).days
        rel = "bugun" if delta == 0 else "ertaga" if delta == 1 else f"{delta} kundan keyin"
        totals: dict[str, float] = {}
        for r in items:
            totals[r["currency"]] = totals.get(r["currency"], 0) + r["amount"]
        tot = ", ".join(f"{fmt_amount(v)} {c}" for c, v in totals.items())
        lines.append(f"🗓 <b>{d.strftime('%d.%m.%Y')}</b> ({rel}) — {tot}")
        lines += [f"  {text_line(r, with_author)}" for r in items]
        lines.append("")
    text = "\n".join(lines)
    await message.answer(text[:4000])
