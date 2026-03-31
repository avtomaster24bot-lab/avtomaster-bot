import asyncio
import logging
import signal
import sys
import os

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage  # для простого FSM
# Для production можно заменить на RedisStorage:
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

# Проверка переменных и файлов
def validate_env():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан")
    if not os.path.exists("alembic.ini"):
        raise FileNotFoundError("alembic.ini не найден")
    if not os.path.exists("avtomaster.db"):
        logging.warning("Файл базы avtomaster.db ещё не существует")

async def run_migrations():
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{os.path.abspath('avtomaster.db')}")
    try:
        command.upgrade(alembic_cfg, "head")
        logging.info("Миграции применены успешно")
    except Exception as e:
        logging.exception(f"Не удалось применить миграции: {e}. init_db выполнит инициализацию.")

def register_routers(dp: Dispatcher):
    # Админские роутеры
    admin_routers = [
        station_admin.router, wash_admin.router, tow_admin.router,
        supplier_admin.router, urgent.router, roadside_admin.router,
        admin_global.router, admin_regional.router, part_tender.router,
        subscription_admin.router, business_registration.router, service_book.router
    ]
    for r in admin_routers:
        dp.include_router(r)

    # Клиентские роутеры
    client_routers = [
        common.router, client.router, settings.router,
        price.router, advisor.router
    ]
    for r in client_routers:
        dp.include_router(r)

    logging.info(f"Роутеры зарегистрированы: админских={len(admin_routers)}, клиентских={len(client_routers)}")

async def shutdown(dp: Dispatcher, bot: Bot):
    logging.info("Завершение работы бота...")
    await dp.storage.close()
    await bot.session.close()
    logging.info("Бот и хранилище корректно закрыты")

async def main():
    setup_logging(LOG_LEVEL)
    logger = logging.getLogger(__name__)

    try:
        validate_env()
    except Exception as e:
        logger.critical(f"Ошибка конфигурации: {e}")
        sys.exit(1)

    await run_migrations()
    await init_db()

    storage = MemoryStorage()  # SQLite FSM
    # Для Redis:
    # storage = RedisStorage.from_url("redis://localhost:6379/0")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=storage)

    # Middleware
    dp.message.middleware(RoleMiddleware())
    dp.callback_query.middleware(RoleMiddleware())

    # Роутеры
    register_routers(dp)

    # Команды
    await bot.set_my_commands([
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="help", description="Помощь")
    ])

    # Scheduler
    try:
        start_scheduler(bot)
        logger.info("Scheduler запущен")
    except Exception as e:
        logger.warning(f"Scheduler не запущен: {e}")

    # Graceful shutdown через сигналы
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(dp, bot)))

    logger.info("Бот запущен. Ожидание событий...")

    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.exception(f"Polling завершился с ошибкой: {e}")
    finally:
        await shutdown(dp, bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Выход по запросу пользователя")