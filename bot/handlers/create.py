"""Yangi xarajat zayavkasini yaratish (bosqichma-bosqich)."""
from datetime import date

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import db
from ..fieldinput import ask_field, parse_field_callback, parse_field_message
from ..keyboards import (BTN_NEW, btn, cancel_kb, currency_kb, date_kb, decision_kb, ikb,
                         main_menu)
from ..notify import notify
from ..render import fmt_field_value, render_body, render_card
from ..states import NewReq
from ..utils import e, fmt_amount, parse_amount, parse_date, today

router = Router(name="create")


@router.message(F.text == BTN_NEW)
async def new_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(NewReq.title)
    await state.update_data(extra={})
    await message.answer(
        "📝 <b>Yangi xarajat zayavkasi</b>\n\n1️⃣ Xarajat maqsadini yozing — pul nima uchun kerak?",
        reply_markup=cancel_kb(),
    )


@router.message(NewReq.title, F.text)
async def got_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if not 3 <= len(title) <= 500:
        await message.answer("Maqsad 3 dan 500 belgigacha bo'lishi kerak. Qayta yozing:")
        return
    await state.update_data(title=title)
    await state.set_state(NewReq.amount)
    await message.answer("2️⃣ Summani kiriting (masalan: <code>1500000</code> yoki <code>250.50</code>):")


@router.message(NewReq.amount, F.text)
async def got_amount(message: Message, state: FSMContext):
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer("❗ Summa noto'g'ri. Faqat musbat raqam kiriting, masalan: <code>1500000</code>")
        return
    await state.update_data(amount=amount)
    currencies = await db.list_currencies()
    if len(currencies) == 1:
        await state.update_data(currency=currencies[0]["code"])
        await _ask_date(message, state)
        return
    await state.set_state(NewReq.currency)
    await message.answer(f"Summa: <b>{fmt_amount(amount)}</b>\n\n3️⃣ Valyutani tanlang:",
                         reply_markup=currency_kb(currencies, "nc"))


@router.callback_query(NewReq.currency, F.data.startswith("nc:"))
async def got_currency(cb: CallbackQuery, state: FSMContext):
    code = cb.data.split(":", 1)[1]
    await state.update_data(currency=code)
    await cb.message.edit_text(f"💱 Valyuta: <b>{e(code)}</b>")
    await cb.answer()
    await _ask_date(cb.message, state)


@router.message(NewReq.currency)
async def currency_hint(message: Message):
    await message.answer("Iltimos, yuqoridagi tugmalardan valyutani tanlang.")


async def _ask_date(msg: Message, state: FSMContext):
    await state.set_state(NewReq.date)
    await msg.answer("4️⃣ Pul <b>qaysi kunga</b> kerak? Tanlang yoki sanani yozing (KK.OO.YYYY):",
                     reply_markup=date_kb("nd"))


@router.callback_query(NewReq.date, F.data.startswith("nd:"))
async def got_date_cb(cb: CallbackQuery, state: FSMContext):
    d = date.fromisoformat(cb.data.split(":", 1)[1])
    await cb.message.edit_text(f"📅 Kerakli sana: <b>{d.strftime('%d.%m.%Y')}</b>")
    await cb.answer()
    await _after_date(cb.message, state, d)


@router.message(NewReq.date, F.text)
async def got_date_msg(message: Message, state: FSMContext):
    d = parse_date(message.text)
    if not d:
        await message.answer("❗ Sana noto'g'ri. Masalan: <code>15.11.2026</code>")
        return
    if d < today():
        await message.answer("❗ O'tgan sanani tanlab bo'lmaydi. Bugungi yoki keyingi sanani kiriting.")
        return
    await _after_date(message, state, d)


async def _after_date(msg: Message, state: FSMContext, d: date):
    await state.update_data(needed_date=d.isoformat())
    await state.set_state(NewReq.comment)
    await msg.answer("5️⃣ Izoh yozing (ixtiyoriy):", reply_markup=ikb([[btn("⏭ O'tkazib yuborish", "nskip")]]))


@router.message(NewReq.comment, F.text)
async def got_comment(message: Message, state: FSMContext):
    text = message.text.strip()
    if len(text) > 1000:
        await message.answer("Izoh juda uzun (maks. 1000 belgi).")
        return
    await state.update_data(comment=text)
    await _start_fields(message, state)


@router.callback_query(NewReq.comment, F.data == "nskip")
async def skip_comment(cb: CallbackQuery, state: FSMContext):
    await state.update_data(comment="")
    await cb.message.edit_text("💬 Izoh: —")
    await cb.answer()
    await _start_fields(cb.message, state)


# ---------------------------------------------------------------- qo'shimcha maydonlar
async def _start_fields(msg: Message, state: FSMContext):
    fields = await db.list_fields(active_only=True)
    await state.update_data(queue=[f["id"] for f in fields])
    await _next_field(msg, state)


async def _next_field(msg: Message, state: FSMContext):
    data = await state.get_data()
    queue = data.get("queue", [])
    while queue:
        field = await db.get_field(queue[0])
        if field and field["active"]:
            await state.set_state(NewReq.field)
            await state.update_data(cur_field=field["id"], queue=queue)
            await ask_field(msg, field, "nfv")
            return
        queue = queue[1:]
    await state.update_data(queue=[])
    await _confirm(msg, state)


async def _store_field(msg: Message, state: FSMContext, value):
    data = await state.get_data()
    extra = data.get("extra", {})
    if value is not None:
        extra[str(data["cur_field"])] = value
    await state.update_data(extra=extra, queue=data.get("queue", [])[1:])
    await _next_field(msg, state)


@router.callback_query(NewReq.field, F.data.startswith("nfv:"))
async def field_cb(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    field = await db.get_field(data.get("cur_field", 0))
    if not field:
        await cb.answer()
        await _store_field(cb.message, state, None)
        return
    ok, value = parse_field_callback(field, cb.data)
    if not ok:
        await cb.answer(str(value), show_alert=True)
        return
    await cb.message.edit_text(f"🧩 {e(field['name'])}: <b>{fmt_field_value(field, value)}</b>")
    await cb.answer()
    await _store_field(cb.message, state, value)


@router.message(NewReq.field)
async def field_msg(message: Message, state: FSMContext):
    data = await state.get_data()
    field = await db.get_field(data.get("cur_field", 0))
    if not field:
        await _store_field(message, state, None)
        return
    ok, value = parse_field_message(field, message)
    if not ok:
        await message.answer(f"❗ {value}")
        return
    await _store_field(message, state, value)


# ---------------------------------------------------------------- tasdiqlash va yuborish
async def _confirm(msg: Message, state: FSMContext):
    data = await state.get_data()
    fields = await db.list_fields()
    body = render_body(data["title"], data["amount"], data["currency"], data["needed_date"],
                       data.get("comment", ""), data.get("extra", {}), fields)
    await state.set_state(NewReq.confirm)
    await msg.answer(
        "📋 <b>Zayavkani tekshiring:</b>\n\n" + "\n".join(body) + "\n\nYuborilsinmi?",
        reply_markup=ikb([[btn("📤 Yuborish", "nsend"), btn("✖️ Bekor qilish", "ncancel")]]),
    )


@router.callback_query(NewReq.confirm, F.data == "nsend")
async def send_request(cb: CallbackQuery, state: FSMContext, user: dict, bot: Bot):
    data = await state.get_data()
    await state.clear()
    rid = await db.create_request(user["id"], data["title"], data["amount"], data["currency"],
                                  data["needed_date"], data.get("comment", ""), data.get("extra", {}))
    await db.add_history(rid, user["id"], "created")
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.answer("Yuborildi")
    await cb.message.answer(
        f"✅ Zayavka <b>#{rid}</b> yuborildi!\n"
        f"Holati: ⏳ Kutilmoqda. Qaror qabul qilinganda sizga xabar keladi.\n\n"
        f"Ko'rish: /r{rid}",
        reply_markup=main_menu(user),
    )
    req = await db.get_request(rid)
    fields = await db.list_fields()
    approvers = [i for i in await db.user_ids_by_roles(["approver", "admin", "superadmin"]) if i != user["id"]]
    await notify(bot, approvers, "🆕 <b>Yangi zayavka!</b>\n\n" + render_card(req, fields), decision_kb(rid))


@router.callback_query(NewReq.confirm, F.data == "ncancel")
async def cancel_request(cb: CallbackQuery, state: FSMContext, user: dict):
    await state.clear()
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.answer()
    await cb.message.answer("✖️ Zayavka bekor qilindi.", reply_markup=main_menu(user))


@router.message(NewReq.title)
@router.message(NewReq.amount)
@router.message(NewReq.date)
@router.message(NewReq.comment)
@router.message(NewReq.confirm)
async def text_expected(message: Message):
    await message.answer("Iltimos, matn yuboring yoki tugmalardan foydalaning. Bekor qilish: /cancel")
