"""Admin panel: foydalanuvchilar/rollar, qo'shimcha maydonlar, valyutalar."""
import re

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import db, services
from ..keyboards import BTN_ADMIN, abort_row, btn, ikb, role_assign_kb
from ..states import AddCurrency, AddField, EditOptions, RenameField
from ..utils import FIELD_TYPES, ROLE_ERRORS, ROLES, allowed_roles, can, e, role_change_error, short

router = Router(name="admin")

USERS_PAGE = 10


async def admin_only(event, user: dict | None = None) -> bool:
    """Filter: faqat admin."""
    return can(user, "admin")


router.message.filter(admin_only)
router.callback_query.filter(admin_only)


async def _safe_edit(msg: Message, text: str, kb=None):
    try:
        await msg.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        await msg.answer(text, reply_markup=kb)


def _panel_kb():
    return ikb([
        [btn("👥 Foydalanuvchilar va rollar", "adm:users:0")],
        [btn("🧩 Qo'shimcha maydonlar", "adm:fields")],
        [btn("💱 Valyutalar", "adm:cur")],
    ])


PANEL_TEXT = "⚙️ <b>Admin panel</b>\n\nNimani sozlaysiz?"


@router.message(F.text == BTN_ADMIN)
async def panel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(PANEL_TEXT, reply_markup=_panel_kb())


@router.callback_query(F.data == "adm:panel")
async def panel_cb(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await _safe_edit(cb.message, PANEL_TEXT, _panel_kb())
    await cb.answer()


# ---------------------------------------------------------------- foydalanuvchilar
@router.callback_query(F.data.startswith("adm:users:"))
async def users_list(cb: CallbackQuery):
    page = int(cb.data.split(":")[2])
    total = await db.count_users()
    users = await db.list_users(page * USERS_PAGE, USERS_PAGE)
    rows = [[btn(f"{ROLES[u['role']].split()[0]} {short(u['full_name'], 24)} · {u['req_count']} ta", f"adm:u:{u['id']}")]
            for u in users]
    nav = []
    if page > 0:
        nav.append(btn("⬅️", f"adm:users:{page - 1}"))
    if (page + 1) * USERS_PAGE < total:
        nav.append(btn("➡️", f"adm:users:{page + 1}"))
    rows.append(nav)
    rows.append([btn("⬅️ Admin panel", "adm:panel")])
    legend = "  ".join(f"{v.split()[0]} {v.split(maxsplit=1)[1]}" for v in ROLES.values())
    await _safe_edit(cb.message, f"👥 <b>Foydalanuvchilar</b> ({total})\n\n<i>{legend}</i>\n\nRolni o'zgartirish uchun tanlang:",
                     ikb(rows))
    await cb.answer()


@router.callback_query(F.data.startswith("adm:u:"))
async def user_card(cb: CallbackQuery, user: dict):
    uid = int(cb.data.split(":")[2])
    u = await db.get_user(uid)
    if not u:
        await cb.answer("Topilmadi", show_alert=True)
        return
    uname = f"@{e(u['username'])}" if u["username"] else "—"
    text = (f"👤 <b>{e(u['full_name'])}</b>\nUsername: {uname}\nID: <code>{u['id']}</code>\n"
            f"Rol: <b>{ROLES[u['role']]}</b>\n\n")
    # Faqat shu admin haqiqatan bera oladigan rollar ko'rsatiladi
    roles = [r for r in allowed_roles(user) if r != u["role"] and role_change_error(user, u, r) is None]
    if roles:
        text += "Yangi rolni tanlang:"
        kb = role_assign_kb(uid, roles)
    else:
        err = role_change_error(user, u, "user") or "forbidden"
        text += f"🔒 {ROLE_ERRORS[err]}."
        kb = ikb([])
    kb.inline_keyboard.append([btn("⬅️ Ro'yxatga", "adm:users:0")])
    await _safe_edit(cb.message, text, kb)
    await cb.answer()


@router.callback_query(F.data.startswith("adm:r:"))
async def set_role(cb: CallbackQuery, user: dict, bot: Bot):
    _, _, uid, role = cb.data.split(":")
    uid = int(uid)
    target = await db.get_user(uid)
    if not target:
        await cb.answer("Topilmadi", show_alert=True)
        return
    err = role_change_error(user, target, role)
    if err:
        await cb.answer(ROLE_ERRORS[err], show_alert=True)
        return
    await services.set_role(bot, user, target, role)
    await cb.answer(f"Rol: {ROLES[role]}")
    await _safe_edit(cb.message, f"✅ <b>{e(target['full_name'])}</b> — rol: {ROLES[role]}",
                     ikb([[btn("⬅️ Foydalanuvchilar", "adm:users:0")]]))


# ---------------------------------------------------------------- maydonlar
async def _fields_view():
    fields = await db.list_fields()
    lines = ["🧩 <b>Qo'shimcha maydonlar</b>",
             "Bu maydonlar har bir yangi zayavkada so'raladi (masalan: Bo'lim, Loyiha, Kategoriya, Chek rasmi).", ""]
    rows = []
    for f in fields:
        flags = ("✅" if f["active"] else "⏸") + (" ❗" if f["required"] else "")
        rows.append([btn(f"{flags} {f['name']} · {FIELD_TYPES[f['type']].split()[0]}", f"adm:f:{f['id']}")])
    if not fields:
        lines.append("Hozircha qo'shimcha maydon yo'q.")
    lines.append("✅ faol · ⏸ o'chirilgan · ❗ majburiy")
    rows.append([btn("➕ Yangi maydon", "adm:fadd")])
    rows.append([btn("⬅️ Admin panel", "adm:panel")])
    return "\n".join(lines), ikb(rows)


@router.callback_query(F.data == "adm:fields")
async def fields_list(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    text, kb = await _fields_view()
    await _safe_edit(cb.message, text, kb)
    await cb.answer()


async def _field_card(msg: Message, fid: int, edit: bool = True):
    f = await db.get_field(fid)
    if not f:
        text, kb = await _fields_view()
    else:
        text = (f"🧩 <b>{e(f['name'])}</b>\nTuri: {FIELD_TYPES[f['type']]}\n"
                f"Holat: {'✅ faol' if f['active'] else '⏸ o‘chirilgan'}\n"
                f"Majburiy: {'ha' if f['required'] else 'yo‘q'}")
        if f["type"] == "choice":
            text += "\nVariantlar: " + ", ".join(e(o) for o in f["options"])
        fid = f["id"]
        rows = [
            [btn("⏸ O'chirish" if f["active"] else "▶️ Yoqish", f"adm:fa:{fid}"),
             btn("Majburiy emas" if f["required"] else "❗ Majburiy qilish", f"adm:fr:{fid}")],
            [btn("✏️ Nomini o'zgartirish", f"adm:fn:{fid}"), btn("⬆️ Yuqoriga", f"adm:fu:{fid}")],
        ]
        if f["type"] == "choice":
            rows.append([btn("📝 Variantlarni o'zgartirish", f"adm:fo:{fid}")])
        rows.append([btn("🗑 O'chirib tashlash", f"adm:fd:{fid}")])
        rows.append([btn("⬅️ Maydonlar", "adm:fields")])
        kb = ikb(rows)
    if edit:
        await _safe_edit(msg, text, kb)
    else:
        await msg.answer(text, reply_markup=kb)


@router.callback_query(F.data.regexp(r"^adm:f:\d+$"))
async def field_card(cb: CallbackQuery):
    await _field_card(cb.message, int(cb.data.split(":")[2]))
    await cb.answer()


@router.callback_query(F.data.startswith("adm:fa:"))
async def field_toggle_active(cb: CallbackQuery, user: dict):
    fid = int(cb.data.split(":")[2])
    f = await db.get_field(fid)
    if f:
        await services.update_field(user, f, active=0 if f["active"] else 1)
    await _field_card(cb.message, fid)
    await cb.answer()


@router.callback_query(F.data.startswith("adm:fr:"))
async def field_toggle_required(cb: CallbackQuery, user: dict):
    fid = int(cb.data.split(":")[2])
    f = await db.get_field(fid)
    if f:
        await services.update_field(user, f, required=0 if f["required"] else 1)
    await _field_card(cb.message, fid)
    await cb.answer()


@router.callback_query(F.data.startswith("adm:fu:"))
async def field_up(cb: CallbackQuery, user: dict):
    f = await db.get_field(int(cb.data.split(":")[2]))
    if f:
        await services.move_field_up(user, f)
    await cb.answer("Tartib o'zgardi")
    text, kb = await _fields_view()
    await _safe_edit(cb.message, text, kb)


@router.callback_query(F.data.regexp(r"^adm:fd:\d+$"))
async def field_delete_ask(cb: CallbackQuery):
    fid = int(cb.data.split(":")[2])
    await cb.message.edit_reply_markup(reply_markup=ikb([
        [btn("🗑 Ha, o'chirilsin", f"adm:fdy:{fid}"), btn("⬅️ Yo'q", f"adm:f:{fid}")],
    ]))
    await cb.answer("Eski zayavkalardagi bu maydon qiymatlari ko'rinmay qoladi. Faqat yashirish uchun ⏸ ni ishlating.",
                    show_alert=True)


@router.callback_query(F.data.startswith("adm:fdy:"))
async def field_delete(cb: CallbackQuery, user: dict):
    f = await db.get_field(int(cb.data.split(":")[2]))
    if f:
        await services.delete_field(user, f)
    await cb.answer("O'chirildi")
    text, kb = await _fields_view()
    await _safe_edit(cb.message, text, kb)


@router.callback_query(F.data.startswith("adm:fn:"))
async def field_rename_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(RenameField.name)
    await state.update_data(fid=int(cb.data.split(":")[2]))
    await cb.message.answer("Maydonning yangi nomini yozing:", reply_markup=ikb([abort_row()]))
    await cb.answer()


@router.message(RenameField.name, F.text)
async def field_rename(message: Message, state: FSMContext, user: dict):
    name = message.text.strip()
    if not 1 <= len(name) <= 60:
        await message.answer("Nom 1–60 belgi bo'lishi kerak.")
        return
    fid = (await state.get_data())["fid"]
    await state.clear()
    f = await db.get_field(fid)
    if f:
        await services.update_field(user, f, name=name)
    await _field_card(message, fid, edit=False)


@router.callback_query(F.data.startswith("adm:fo:"))
async def field_options_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(EditOptions.options)
    await state.update_data(fid=int(cb.data.split(":")[2]))
    await cb.message.answer(
        "Yangi variantlarni har birini yangi qatorda (yoki vergul bilan) yozing.\n"
        "<i>Eslatma: eski zayavkalardagi qiymatlar o'zgarmaydi.</i>",
        reply_markup=ikb([abort_row()]),
    )
    await cb.answer()


def _parse_options(text: str) -> list[str]:
    parts = re.split(r"[\n,;]", text)
    seen, out = set(), []
    for p in parts:
        p = p.strip()[:40]
        if p and p.lower() not in seen:
            seen.add(p.lower())
            out.append(p)
    return out[:30]


@router.message(EditOptions.options, F.text)
async def field_options(message: Message, state: FSMContext, user: dict):
    opts = _parse_options(message.text)
    if len(opts) < 2:
        await message.answer("Kamida 2 ta variant kiriting.")
        return
    fid = (await state.get_data())["fid"]
    await state.clear()
    f = await db.get_field(fid)
    if f:
        await services.update_field(user, f, options=opts)
    await _field_card(message, fid, edit=False)


# --- yangi maydon qo'shish
@router.callback_query(F.data == "adm:fadd")
async def field_add_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AddField.name)
    await cb.message.answer("➕ <b>Yangi maydon</b>\n\nMaydon nomini yozing (masalan: <i>Bo'lim</i>, <i>Loyiha</i>, <i>Chek rasmi</i>):",
                            reply_markup=ikb([abort_row()]))
    await cb.answer()


@router.message(AddField.name, F.text)
async def field_add_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not 1 <= len(name) <= 60:
        await message.answer("Nom 1–60 belgi bo'lishi kerak.")
        return
    await state.update_data(name=name)
    await state.set_state(AddField.type)
    rows = [[btn(label, f"adm:ft:{key}")] for key, label in FIELD_TYPES.items()]
    rows.append(abort_row())
    await message.answer(f"«{e(name)}» maydoni turi qanday?", reply_markup=ikb(rows))


@router.callback_query(AddField.type, F.data.startswith("adm:ft:"))
async def field_add_type(cb: CallbackQuery, state: FSMContext):
    ftype = cb.data.split(":")[2]
    if ftype not in FIELD_TYPES:
        await cb.answer()
        return
    await state.update_data(type=ftype, options=[])
    await cb.message.edit_text(f"Turi: {FIELD_TYPES[ftype]}")
    await cb.answer()
    if ftype == "choice":
        await state.set_state(AddField.options)
        await cb.message.answer("Variantlarni har birini yangi qatorda (yoki vergul bilan) yozing.\n"
                                "Masalan: <code>Marketing, IT, Logistika, Ofis</code>")
    else:
        await _ask_required(cb.message, state)


@router.message(AddField.options, F.text)
async def field_add_options(message: Message, state: FSMContext):
    opts = _parse_options(message.text)
    if len(opts) < 2:
        await message.answer("Kamida 2 ta variant kiriting.")
        return
    await state.update_data(options=opts)
    await _ask_required(message, state)


async def _ask_required(msg: Message, state: FSMContext):
    await state.set_state(AddField.required)
    await msg.answer("Bu maydon majburiymi?",
                     reply_markup=ikb([[btn("❗ Majburiy", "adm:freq:1"), btn("Ixtiyoriy", "adm:freq:0")], abort_row()]))


@router.callback_query(AddField.required, F.data.startswith("adm:freq:"))
async def field_add_required(cb: CallbackQuery, state: FSMContext, user: dict):
    data = await state.get_data()
    await state.clear()
    fid = await services.add_field(user, data["name"], data["type"], data.get("options", []), cb.data.endswith(":1"))
    await cb.answer("Maydon qo'shildi")
    await cb.message.edit_text(f"✅ «{e(data['name'])}» maydoni qo'shildi. Endi yangi zayavkalarda so'raladi.")
    await _field_card(cb.message, fid, edit=False)


# ---------------------------------------------------------------- valyutalar
async def _cur_view():
    curs = await db.list_currencies(active_only=False)
    rows = []
    codes = [btn(("✅ " if c["active"] else "⏸ ") + c["code"], f"adm:ct:{c['code']}") for c in curs]
    for i in range(0, len(codes), 3):
        rows.append(codes[i:i + 3])
    rows.append([btn("➕ Valyuta qo'shish", "adm:cadd")])
    rows.append([btn("⬅️ Admin panel", "adm:panel")])
    return "💱 <b>Valyutalar</b>\n\nBosib yoqing / o'chiring. O'chirilgan valyuta yangi zayavkalarda chiqmaydi.", ikb(rows)


@router.callback_query(F.data == "adm:cur")
async def cur_list(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    text, kb = await _cur_view()
    await _safe_edit(cb.message, text, kb)
    await cb.answer()


@router.callback_query(F.data.startswith("adm:ct:"))
async def cur_toggle(cb: CallbackQuery, user: dict):
    code = cb.data.split(":")[2]
    curs = await db.list_currencies(active_only=True)
    if len(curs) == 1 and curs[0]["code"] == code:
        await cb.answer("Kamida bitta valyuta faol bo'lishi kerak", show_alert=True)
        return
    await services.toggle_currency(user, code)
    text, kb = await _cur_view()
    await _safe_edit(cb.message, text, kb)
    await cb.answer()


@router.callback_query(F.data == "adm:cadd")
async def cur_add_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AddCurrency.code)
    await cb.message.answer("Valyuta kodini yozing (3 harf, masalan: <code>KZT</code>, <code>CNY</code>, <code>GBP</code>):",
                            reply_markup=ikb([abort_row()]))
    await cb.answer()


@router.message(AddCurrency.code, F.text)
async def cur_add(message: Message, state: FSMContext, user: dict):
    code = message.text.strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", code):
        await message.answer("Kod 3 ta lotin harfidan iborat bo'lishi kerak.")
        return
    await state.clear()
    await services.add_currency(user, code)
    text, kb = await _cur_view()
    await message.answer(f"✅ {code} qo'shildi.\n\n" + text, reply_markup=kb)
