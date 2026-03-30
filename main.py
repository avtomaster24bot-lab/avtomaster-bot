import asyncio
import logging
import signal
import sys
import os

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
# Для production:
# from aiogram.fsm.storage.redis import RedisStorage

from aiogram.types import BotCommand

from config import BOT_TOKEN, LOG_LEVEL
from handlers import (
    common, client, station_admin, wash_admin, tow_admin, supplier_admin,
    urgent, settings, subscription_admin, business_registration,
    admin_global, admin_regional, part_tender, roadside_admin, price, advisor,
    service_book
)
from middlewares.role_middleware import RoleMiddleware
from utils.logger import setup_logging
from init_db import init_db
from scheduler import start_scheduler

from alembic.config import Config
from alembic import command

# -------------------- Проверка окружения --------------------
def validate_env():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN не задан")

    if not os.path.exists("alembic.ini"):
        raise FileNotFoundError("❌ Файл alembic.ini не найден")

# -------------------- Миграции --------------------
async def run_migrations():
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option(
        "sqlalchemy.url",
        f"sqlite:///{os.path.abspath('avtomaster.db')}"
    )

    try:
        command.upgrade(alembic_cfg, "head")
        logging.info("✅ Миграции применены")
    except Exception as e:
        logging.warning(f"⚠️ Ошибка миграций: {e}")

# -------------------- Роутеры --------------------
def register_routers(dp: Dispatcher):
    admin_routers = [
        station_admin.router, wash_admin.router, tow_admin.router,
        supplier_admin.router, urgent.router, roadside_admin.router,
        admin_global.router, admin_regional.router, part_tender.router,
        subscription_admin.router, business_registration.router, service_book.router
    ]

    client_routers = [
        common.router, client.router, settings.router,
        price.router, advisor.router
    ]

    for router in admin_routers + client_routers:
        dp.include_router(router)

    logging.info(f"✅ Роутеры подключены: {len(admin_routers + client_routers)}")

# -------------------- Shutdown --------------------
async def shutdown(bot: Bot, dp: Dispatcher):
    logging.info("🛑 Завершение работы...")

    await dp.storage.close()
    await bot.session.close()

    logging.info("✅ Бот остановлен корректно")

# -------------------- MAIN --------------------
async def main():
    setup_logging(LOG_LEVEL)
    logger = logging.getLogger(__name__)

    # Проверка окружения
    try:
        validate_env()
    except Exception as e:
        logger.critical(f"Ошибка конфигурации: {e}")
        sys.exit(1)

    # База
    await run_migrations()
    await init_db()

    # Storage (потом заменишь на Redis)
    storage = MemoryStorage()
    # storage = RedisStorage.from_url("redis://localhost:6379/0")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=storage)

    # Middleware
    role_middleware = RoleMiddleware()
    dp.message.middleware(role_middleware)
    dp.callback_query.middleware(role_middleware)

    # Роутеры
    register_routers(dp)

    # Команды
    await bot.set_my_commands([
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="help", description="Помощь"),
    ])

    # Scheduler
    try:
        start_scheduler(bot)
        logger.info("✅ Scheduler запущен")
    except Exception as e:
        logger.warning(f"⚠️ Scheduler не запущен: {e}")

    # Сигналы остановки
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.create_task(shutdown(bot, dp))
        )

    logger.info("🚀 Бот запущен")

    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.exception(f"❌ Ошибка polling: {e}")
    finally:
        await shutdown(bot, dp)

# -------------------- ENTRY --------------------
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("⛔ Бот остановлен вручную")
