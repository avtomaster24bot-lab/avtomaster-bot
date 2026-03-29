# main.py
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from config import BOT_TOKEN, LOG_LEVEL
from database import db
from handlers import (
    common, client, station_admin, wash_admin, tow_admin, supplier_admin,
    urgent, settings, subscription_admin, business_registration,
    admin_global, admin_regional, part_tender, roadside_admin, price, advisor,
    service_book  # добавлен
)
from middlewares.role_middleware import RoleMiddleware
from utils.logger import setup_logging
from init_db import init_db 
from scheduler import start_scheduler

from alembic.config import Config
from alembic import command
import os

async def run_migrations():
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{os.path.abspath('avtomaster.db')}")
    try:
        command.upgrade(alembic_cfg, "head")
        logging.info("Миграции применены успешно")
    except Exception as e:
        logging.warning(f"Не удалось применить миграции: {e}. База данных будет инициализирована через init_db.")

async def main():
    setup_logging(LOG_LEVEL)
    logger = logging.getLogger(__name__)

    await init_db()
    await run_migrations()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.middleware(RoleMiddleware())
    dp.callback_query.middleware(RoleMiddleware())

    # Административные роутеры
    dp.include_router(station_admin.router)
    dp.include_router(wash_admin.router)
    dp.include_router(tow_admin.router)
    dp.include_router(supplier_admin.router)
    dp.include_router(urgent.router)
    dp.include_router(roadside_admin.router)
    dp.include_router(admin_global.router)
    dp.include_router(admin_regional.router)
    dp.include_router(part_tender.router)
    dp.include_router(subscription_admin.router)
    dp.include_router(business_registration.router)
    dp.include_router(service_book.router)          # подключён

    # Клиентские роутеры
    dp.include_router(common.router)
    dp.include_router(client.router)
    dp.include_router(settings.router)
    dp.include_router(price.router)
    dp.include_router(advisor.router)

    await bot.set_my_commands([
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="help", description="Помощь"),
    ])

    start_scheduler(bot)

    logger.info("Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())