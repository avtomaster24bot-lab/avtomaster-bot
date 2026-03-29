import asyncio
import pytest
import aiosqlite
import os
from database import db
from init_db import init_db

TEST_DB_PATH = "test.db"

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="function", autouse=True)
async def setup_test_db():
    # Создаём таблицы в тестовой базе
    await init_db(TEST_DB_PATH)
    yield
    # Закрываем соединения и удаляем файл
    try:
        await db._close_all()
    except AttributeError:
        pass
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)

@pytest.fixture
async def db_conn():
    async with aiosqlite.connect(TEST_DB_PATH) as conn:
        await conn.execute("PRAGMA foreign_keys = ON")
        await conn.execute("PRAGMA journal_mode = WAL")
        yield conn

@pytest.fixture
async def db_session():
    async with db.session() as conn:
        yield conn