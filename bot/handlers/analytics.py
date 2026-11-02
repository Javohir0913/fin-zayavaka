"""Dashboard, grafiklar, Excel eksport va qisqa hisobot."""
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InputMediaPhoto, Message

from .. import reports
from ..keyboards import BTN_DASH, BTN_REPORT, btn, ikb
from ..utils import can, today

router = Router(name="analytics")


async def analytics_only(event, user: dict | None = None) -> bool:
    return can(user, "analytics")


router.message.filter(analytics_only)
router.callback_query.filter(analytics_only)


def _dash_kb(period: str):
    p = [btn(("• " if k == period else "") + v, f"db:{k}") for k, v in reports.PERIODS.items()]
    return ikb([p[:3], p[3:], [btn("📈 Grafiklar", f"dbc:{period}"), btn("📥 Excel", f"dbx:{period}")]])


@router.message(F.text == BTN_DASH)
async def dashboard(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(await reports.dashboard_text("month"), reply_markup=_dash_kb("month"))


@router.callback_query(F.data.startswith("db:"))
async def dashboard_period(cb: CallbackQuery):
    period = cb.data.split(":")[1]
    if period not in reports.PERIODS:
        await cb.answer()
        return
    try:
        await cb.message.edit_text(await reports.dashboard_text(period), reply_markup=_dash_kb(period))
    except TelegramBadRequest:
        pass
    await cb.answer()


@router.callback_query(F.data.startswith("dbc:"))
async def dashboard_charts(cb: CallbackQuery):
    period = cb.data.split(":")[1]
    await cb.answer("Grafiklar tayyorlanmoqda…")
    images = await reports.charts(period)
    if not images:
        await cb.message.answer("Bu davrda grafik uchun ma'lumot yo'q.")
        return
    media = [InputMediaPhoto(media=BufferedInputFile(data, f"{i}.png"), caption=name)
             for i, (name, data) in enumerate(images)]
    await cb.message.answer_media_group(media[:10])


@router.callback_query(F.data.startswith("dbx:"))
async def dashboard_excel(cb: CallbackQuery):
    period = cb.data.split(":")[1]
    await cb.answer("Excel tayyorlanmoqda…")
    data = await reports.excel(period)
    name = f"zayavkalar_{period}_{today().strftime('%Y%m%d')}.xlsx"
    await cb.message.answer_document(BufferedInputFile(data, name),
                                     caption=f"📥 Zayavkalar — {reports.PERIODS[period]}")


@router.message(F.text == BTN_REPORT)
async def short_report(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(await reports.short_report())
