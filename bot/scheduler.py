"""Har kuni REPORT_HOUR da tasdiqlovchi/kuzatuvchi/adminlarga qisqa hisobot yuboradi."""
import asyncio
import logging
from datetime import datetime

from aiogram import Bot

from . import db, reports
from .config import REPORT_HOUR, TZ
from .notify import notify

log = logging.getLogger(__name__)


async def scheduler_loop(bot: Bot) -> None:
    if REPORT_HOUR < 0:
        return
    while True:
        try:
            now = datetime.now(TZ)
            today = now.date().isoformat()
            if now.hour >= REPORT_HOUR and await db.get_setting("last_daily_report") != today:
                await db.set_setting("last_daily_report", today)
                text = await reports.short_report()
                ids = await db.user_ids_by_roles(["superadmin", "admin", "approver", "viewer"])
                sent = await notify(bot, ids, "🌅 <b>Kunlik hisobot</b>\n\n" + text)
                log.info("Kunlik hisobot yuborildi: %s ta", sent)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Rejalashtiruvchida xato")
        await asyncio.sleep(60)
