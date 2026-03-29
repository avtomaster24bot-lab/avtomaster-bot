# migrate_data.py
import aiosqlite
import asyncio
import logging

OLD_DB_PATH = "avtomaster.db"  # если старая база называется иначе, измените
NEW_DB_PATH = "avtomaster.db"  # новая база (но она уже существует, мы не будем её перезаписывать)

# Список таблиц для переноса (порядок важен: сначала те, на которые ссылаются внешние ключи)
TABLES = [
    "users",
    "cities",
    "categories",
    "subcategories",
    "stations",
    "station_categories",
    "car_washes",
    "wash_slots",
    "tow_trucks",
    "tow_offers",
    "suppliers",
    "parts",
    "part_orders",
    "reviews",
    "user_cars",
    "service_records",
    "price_list",
    "subscriptions",
    "transactions",
    "paid_diagnostics",
    "ai_chat_history",
    "part_requests",
    "part_offers",
    "partner_requests",
    "roadside_offers",
    "service_providers",
    "service_offers",
    "requests",
]

async def copy_table(old_conn: aiosqlite.Connection, new_conn: aiosqlite.Connection, table: str):
    """Копирует все строки из таблицы в старой БД в новую, игнорируя отсутствующие колонки."""
    # Получаем список колонок в старой таблице
    cursor = await old_conn.execute(f"PRAGMA table_info({table})")
    old_columns = [col[1] for col in await cursor.fetchall()]
    if not old_columns:
        logging.warning(f"Таблица {table} не найдена в старой БД, пропускаем")
        return

    # Получаем список колонок в новой таблице
    cursor = await new_conn.execute(f"PRAGMA table_info({table})")
    new_columns = [col[1] for col in await cursor.fetchall()]
    if not new_columns:
        logging.warning(f"Таблица {table} не найдена в новой БД, пропускаем")
        return

    # Определяем пересекающиеся колонки (копируем только те, которые есть в обеих таблицах)
    common_cols = [col for col in old_columns if col in new_columns]
    if not common_cols:
        logging.warning(f"Нет общих колонок для таблицы {table}, пропускаем")
        return

    # Загружаем данные из старой таблицы
    select_cols = ", ".join(f'"{col}"' for col in common_cols)
    cursor = await old_conn.execute(f"SELECT {select_cols} FROM {table}")
    rows = await cursor.fetchall()
    if not rows:
        logging.info(f"Таблица {table} пуста, пропускаем")
        return

    # Формируем INSERT-запрос
    insert_cols = ", ".join(f'"{col}"' for col in common_cols)
    placeholders = ", ".join(["?"] * len(common_cols))
    insert_sql = f"INSERT OR IGNORE INTO {table} ({insert_cols}) VALUES ({placeholders})"

    # Выполняем вставку
    await new_conn.executemany(insert_sql, rows)
    await new_conn.commit()
    logging.info(f"Скопировано {len(rows)} записей в таблицу {table}")

async def migrate():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logging.info("Начинаем перенос данных...")

    async with aiosqlite.connect(OLD_DB_PATH) as old_conn:
        async with aiosqlite.connect(NEW_DB_PATH) as new_conn:
            # Отключаем проверку внешних ключей на время вставки, чтобы не было ошибок
            await new_conn.execute("PRAGMA foreign_keys = OFF")
            await new_conn.commit()

            for table in TABLES:
                await copy_table(old_conn, new_conn, table)

            # Включаем проверку внешних ключей обратно
            await new_conn.execute("PRAGMA foreign_keys = ON")
            await new_conn.commit()

            # Копируем последовательности (sqlite_sequence) для автоинкремента
            cursor = await old_conn.execute("SELECT * FROM sqlite_sequence")
            sequences = await cursor.fetchall()
            if sequences:
                await new_conn.executemany("REPLACE INTO sqlite_sequence (name, seq) VALUES (?, ?)", sequences)
                await new_conn.commit()
                logging.info("Скопированы последовательности автоинкремента")

    logging.info("Перенос данных завершён!")

if __name__ == "__main__":
    asyncio.run(migrate())