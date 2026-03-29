import aiosqlite
import asyncio
from config import DATABASE_URL

async def init_db(db_path=None):
    if db_path is None:
        db_path = DATABASE_URL.replace("sqlite:///", "")
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("PRAGMA journal_mode = WAL")

        # Минимальный набор таблиц для запуска
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                telegram_id INTEGER UNIQUE,
                city TEXT,
                role TEXT DEFAULT 'client',
                full_name TEXT,
                phone TEXT,
                display_name_choice TEXT DEFAULT 'real_name',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS cities (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY,
                name TEXT,
                city_id INTEGER,
                FOREIGN KEY (city_id) REFERENCES cities(id)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS subcategories (
                id INTEGER PRIMARY KEY,
                name TEXT,
                category_id INTEGER,
                FOREIGN KEY (category_id) REFERENCES categories(id)
            )
        ''')
        # Добавьте другие таблицы позже, но пока достаточно

        await db.commit()

        # Добавим город, если нет
        cursor = await db.execute("SELECT COUNT(*) FROM cities")
        count = await cursor.fetchone()
        if count[0] == 0:
            await db.execute("INSERT INTO cities (name) VALUES ('Талдыкорган')")
            await db.commit()

    print("✅ База данных успешно инициализирована (минимальная версия).")

if __name__ == "__main__":
    asyncio.run(init_db())