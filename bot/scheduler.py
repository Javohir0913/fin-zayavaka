"""Kunlik vazifalar: REPORT_HOUR da qisqa hisobot (-1 = o'chiq) va audit logni 3 oylik tozalash."""
import asyncio
import logging
from datetime import datetime

from aiogram import Bot

from . import audit, db, inbox, rates, reports
from .config import REPORT_HOUR, TZ
from .notify import notify

log = logging.getLogger(__name__)


async def scheduler_loop(bot: Bot) -> None:
    while True:
        try:
            now = datetime.now(TZ)
            today = now.date().isoformat()
            # Yangi kun boshlanganda shu kunning kurs qatorlari darhol paydo bo'lsin (yengil COUNT so'rovi)
            await rates.ensure_today()
            # Audit log: 3 oydan eski yozuvlar deleted='Y' (kuniga bir marta, jismonan o'chirilmaydi)
            if await db.get_setting("last_audit_purge") != today:
                await db.set_setting("last_audit_purge", today)
                await audit.purge_old(now)
                await inbox.purge_old(now)  # 90 kundan eski bildirishnomalar
            if REPORT_HOUR >= 0 and now.hour >= REPORT_HOUR and await db.get_setting("last_daily_report") != today:
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
