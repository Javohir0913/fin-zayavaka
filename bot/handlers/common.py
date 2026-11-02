from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..keyboards import BTN_APP, BTN_CANCEL, app_link_kb, main_menu
from ..utils import ROLES, can, e

router = Router(name="common")

HELP = """ℹ️ <b>Xarajat zayavkalari boti</b>

➕ <b>Yangi zayavka</b> — pul so'rash: maqsad, summa, valyuta, qaysi kunga kerakligi va qo'shimcha maydonlar.
📋 <b>Mening zayavkalarim</b> — o'z zayavkalaringiz, holat bo'yicha filtr. Kutilayotganini tahrirlash yoki bekor qilish mumkin.
📅 <b>Muddatlar</b> — yaqin kunlarda kerak bo'ladigan va muddati o'tgan zayavkalar.

<b>Tasdiqlovchilar uchun:</b> ⏳ Kutilayotganlar, ✅ tasdiqlash / ❌ rad etish (sabab bilan).
<b>Kuzatuvchi/buxgalter:</b> 📊 Dashboard, grafiklar, Excel eksport, 📝 qisqa hisobot.
<b>Admin:</b> ⚙️ foydalanuvchilar va rollar, qo'shimcha maydonlar, valyutalar.

Buyruqlar: /start, /cancel, /id, <code>/r12</code> — 12-zayavkani ochish."""


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, user: dict):
    await state.clear()
    if user["role"] == "pending":
        await message.answer(
            f"Assalomu alaykum, {e(user['full_name'])}! 👋\n\n"
            "Siz ro'yxatdan o'tdingiz. Administrator sizga rol berganidan so'ng botdan foydalana olasiz."
        )
        return
    if user["role"] == "blocked":
        await message.answer("⛔ Sizning kirishingiz bloklangan.")
        return
    await message.answer(
        f"Assalomu alaykum, <b>{e(user['full_name'])}</b>! 👋\n"
        f"Rolingiz: {ROLES[user['role']]}\n\nQuyidagi menyudan tanlang 👇",
        reply_markup=main_menu(user),
    )
    if app_link_kb():
        await message.answer("📱 Qulay ilova orqali ishlash uchun:", reply_markup=app_link_kb())


@router.message(F.text == BTN_APP)
async def open_app(message: Message, state: FSMContext):
    await state.clear()
    kb = app_link_kb()
    if kb:
        await message.answer("👇 Ilovani ochish uchun bosing:", reply_markup=kb)


@router.message(Command("help"))
async def cmd_help(message: Message, user: dict):
    await message.answer(HELP, reply_markup=main_menu(user))


@router.message(Command("id"))
async def cmd_id(message: Message, user: dict):
    await message.answer(f"Sizning ID: <code>{user['id']}</code>\nRol: {ROLES[user['role']]}")


@router.message(Command("cancel"))
@router.message(F.text == BTN_CANCEL)
async def cmd_cancel(message: Message, state: FSMContext, user: dict):
    await state.clear()
    await message.answer("Bekor qilindi.", reply_markup=main_menu(user))


@router.callback_query(F.data == "ex")
async def cb_abort(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("✖️ Bekor qilindi.")
    await cb.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(cb: CallbackQuery):
    await cb.answer()


def has_perm(user: dict, perm: str) -> bool:
    return can(user, perm)
