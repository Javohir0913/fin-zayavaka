import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, MenuButtonCommands, MenuButtonWebApp, WebAppInfo

from . import config, db, rates
from .handlers import routers
from .middlewares import AuthMiddleware
from .scheduler import scheduler_loop
from .webapp import start_web


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not config.BOT_TOKEN:
        sys.exit("BOT_TOKEN topilmadi: .env.example faylidan .env yarating va tokenni yozing.")
    if not config.ADMIN_IDS:
        logging.warning("ADMIN_IDS bo'sh — hech kim admin bo'lmaydi. .env ga o'z Telegram ID ingizni yozing.")

    await db.init()
    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    auth = AuthMiddleware()
    dp.message.outer_middleware(auth)
    dp.callback_query.outer_middleware(auth)
    dp.include_routers(*routers)

    await bot.set_my_commands([
        BotCommand(command="start", description="Asosiy menyu"),
        BotCommand(command="help", description="Yordam"),
        BotCommand(command="cancel", description="Amalni bekor qilish"),
        BotCommand(command="id", description="Mening ID im"),
    ])
    if config.WEBAPP_URL:
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Ilova", web_app=WebAppInfo(url=config.WEBAPP_URL)))
    else:
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    runner = await start_web(bot)
    task = asyncio.create_task(scheduler_loop(bot))
    rates_task = asyncio.create_task(rates.refresh_loop())
    try:
        await dp.start_polling(bot)
    finally:
        task.cancel()
        rates_task.cancel()
        await runner.cleanup()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
