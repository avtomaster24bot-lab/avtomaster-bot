import aiosqlite
from contextlib import asynccontextmanager
from config import DATABASE_URL

DB_PATH = DATABASE_URL.replace("sqlite:///", "")

class Database:
    @asynccontextmanager
    async def session(self):
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute("PRAGMA foreign_keys = ON")
            await conn.execute("PRAGMA journal_mode = WAL")
            yield conn

db = Database()