"""Tasdiqlovchilarga yuborilgan "🆕 Yangi zayavka!" xabarlari.

Xabar raqamlari saqlanadi va zayavka holati o'zgarganda (bot, web yoki Mini App — farqi yo'q)
hammadagi o'sha bitta xabar tahrirlanadi: sarlavha va kartochka yangilanadi, qaror qilingan
bo'lsa Tasdiqlash / Rad etish tugmalari olib tashlanadi, qayta ochilsa qaytadi.
Yangi xabar yuborilmaydi — chat to'lib ketmaydi.
"""
import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from . import db
from .keyboards import btn, decision_kb, ikb
from .render import render_card

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS decision_messages(
    request_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    PRIMARY KEY(request_id, chat_id, message_id)
);
"""

HEADER = {
    "pending": "🆕 <b>Yangi zayavka!</b>",
    "approved": "✅ <b>Tasdiqlandi</b>",
    "rejected": "❌ <b>Rad etildi</b>",
    "cancelled": "🚫 <b>Bekor qilindi</b>",
}

_locks: dict[int, asyncio.Lock] = {}
_tasks: set[asyncio.Task] = set()


def _payload(req: dict, fields: list[dict]):
    text = HEADER.get(req["status"], "📄") + "\n\n" + render_card(req, fields)
    kb = decision_kb(req["id"]) if req["status"] == "pending" else ikb([[btn("🔎 Batafsil", f"rq:v:{req['id']}")]])
    return text, kb


async def send_new(bot: Bot, user_ids, req: dict, fields: list[dict]) -> None:
    """Yangi zayavka xabarini yuboradi va raqamini eslab qoladi."""
    text, kb = _payload(req, fields)
    for uid in set(user_ids):
        try:
            m = await bot.send_message(uid, text, reply_markup=kb)
        except Exception as ex:  # botni bloklagan va h.k.
            log.warning("Xabar yuborilmadi %s: %s", uid, ex)
            continue
        await db.execute("INSERT OR IGNORE INTO decision_messages(request_id, chat_id, message_id) VALUES(?,?,?)",
                         req["id"], uid, m.message_id)


async def _edit(bot: Bot, chat_id: int, message_id: int, text: str, kb) -> bool:
    """False — xabar endi yo'q (o'chirilgan / bot bloklangan), yozuvni o'chirish mumkin."""
    for _ in range(3):
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=kb)
            return True
        except TelegramRetryAfter as ex:
            await asyncio.sleep(ex.retry_after + 0.5)
        except TelegramBadRequest as ex:
            s = str(ex).lower()
            if "not modified" in s:
                return True
            if "not found" in s or "can't be edited" in s:
                return False
            log.warning("Xabar tahrirlanmadi %s/%s: %s", chat_id, message_id, ex)
            return True
        except TelegramForbiddenError:
            return False
        except Exception as ex:
            log.warning("Xabar tahrirlanmadi %s/%s: %s", chat_id, message_id, ex)
            return True
    return True


async def _sync(bot: Bot, rid: int) -> None:
    lock = _locks.setdefault(rid, asyncio.Lock())
    async with lock:  # ketma-ket o'zgarishlar aralashmasin; har safar eng so'nggi holat olinadi
        req = await db.get_request(rid)
        rows = await db.fetchall("SELECT chat_id, message_id FROM decision_messages WHERE request_id=?", rid)
        if not req or not rows:
            return
        text, kb = _payload(req, await db.list_fields())
        for r in rows:
            if not await _edit(bot, r["chat_id"], r["message_id"], text, kb):
                await db.execute("DELETE FROM decision_messages WHERE request_id=? AND chat_id=? AND message_id=?",
                                 rid, r["chat_id"], r["message_id"])
            await asyncio.sleep(0.05)  # Telegram cheklovi (~30 xabar/soniya) ichida
    if not lock.locked() and _locks.get(rid) is lock:
        _locks.pop(rid, None)


def sync(bot: Bot | None, rid: int) -> None:
    """Holat o'zgardi: barcha tasdiqlovchilardagi xabarni fonda yangilaymiz (javobni kutdirmaymiz)."""
    if bot is None:
        return
    t = asyncio.create_task(_sync(bot, rid))
    _tasks.add(t)
    t.add_done_callback(_done)


def _done(t: asyncio.Task) -> None:
    _tasks.discard(t)
    if not t.cancelled() and t.exception():
        log.error("Xabarlarni yangilashda xato", exc_info=t.exception())
