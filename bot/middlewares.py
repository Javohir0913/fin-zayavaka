from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from . import db
from .keyboards import MENU_BUTTONS, role_assign_kb
from .notify import notify
from .utils import e


class AuthMiddleware(BaseMiddleware):
    """Foydalanuvchini bazaga yozadi, `user` ni handlerlarga uzatadi va ruxsatsizlarni to'xtatadi."""

    async def __call__(self, handler: Callable[[TelegramObject, dict], Awaitable[Any]],
                       event: TelegramObject, data: dict[str, Any]) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return
        if isinstance(event, Message) and event.chat.type != "private":
            return  # bot faqat shaxsiy chatda ishlaydi

        user, is_new = await db.upsert_user(tg_user.id, tg_user.full_name, tg_user.username)
        data["user"] = user

        if is_new and user["role"] == "pending":
            admins = await db.user_ids_by_roles(["admin"])
            uname = f" @{e(tg_user.username)}" if tg_user.username else ""
            await notify(
                data["bot"], admins,
                f"🆕 <b>Yangi foydalanuvchi</b>\n{e(tg_user.full_name)}{uname}\nID: <code>{tg_user.id}</code>\n\nRol tanlang:",
                role_assign_kb(tg_user.id),
            )

        if user["role"] in ("pending", "blocked"):
            if isinstance(event, Message) and (event.text or "").startswith("/start"):
                return await handler(event, data)
            text = ("⛔ Sizning kirishingiz bloklangan." if user["role"] == "blocked"
                    else "🕓 Administrator sizga ruxsat berishini kuting.")
            if isinstance(event, Message):
                await event.answer(text)
            elif isinstance(event, CallbackQuery):
                await event.answer(text, show_alert=True)
            return

        # Jarayon o'rtasida menyu tugmasi bosilsa — jarayonni to'xtatib, tugmani bajaramiz
        if isinstance(event, Message) and event.text in MENU_BUTTONS and data.get("raw_state"):
            await data["state"].clear()
            data["raw_state"] = None
        return await handler(event, data)
