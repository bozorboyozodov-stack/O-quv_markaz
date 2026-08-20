import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database.db import init_db
from handlers import start, student, teacher, admin
from utils.dedup_middleware import DedupMiddleware

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN topilmadi. Railway'da Variables bo'limiga BOT_TOKEN qo'shing.")

    await init_db()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    # Bir xil update (masalan tarmoq sekinligi tufayli Telegram tomonidan
    # qayta yuborilgan xabar) ikki marta ishlanib, botning ikki marta javob
    # berishining oldini oladi.
    dp.update.outer_middleware(DedupMiddleware())

    # Tartib muhim: aniqroq handlerlar (start, admin, teacher) oldin,
    # umumiy student handlerlari keyin ulanadi.
    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(teacher.router)
    dp.include_router(student.router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
