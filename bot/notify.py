import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

log = logging.getLogger(__name__)


async def notify(bot: Bot, user_ids, text: str, kb: InlineKeyboardMarkup | None = None) -> int:
    sent = 0
    for uid in set(user_ids):
        try:
            await bot.send_message(uid, text, reply_markup=kb)
            sent += 1
        except Exception as ex:  # foydalanuvchi botni bloklagan va h.k.
            log.warning("Xabar yuborilmadi %s: %s", uid, ex)
    return sent
