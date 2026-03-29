# migrate_data_v2.py
import aiosqlite
import asyncio
import logging

OLD_DB_PATH = "old_avtomaster.db"
NEW_DB_PATH = "avtomaster.db"

# Полный список таблиц, которые нужно скопировать (включая station_services)
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
    "station_services",  # добавили важную таблицу с ценами
]

async def copy_table(old_conn, new_conn, table):
    logging.info(f"Обработка таблицы {table}...")
    # Получаем колонки старой таблицы
    cursor = await old_conn.execute(f"PRAGMA table_info({table})")
    old_columns = [col[1] for col in await cursor.fetchall()]
    if not old_columns:
        logging.warning(f"Таблица {table} не найдена в старой БД")
        return

    # Получаем колонки новой таблицы
    cursor = await new_conn.execute(f"PRAGMA table_info({table})")
    new_columns = [col[1] for col in await cursor.fetchall()]
    if not new_columns:
        logging.warning(f"Таблица {table} не найдена в новой БД")
        return

    # Находим общие колонки
    common_cols = [col for col in old_columns if col in new_columns]
    if not common_cols:
        logging.warning(f"Нет общих колонок для таблицы {table}")
        return

    # Загружаем данные из старой таблицы
    select_cols = ", ".join(f'"{col}"' for col in common_cols)
    cursor = await old_conn.execute(f"SELECT {select_cols} FROM {table}")
    rows = await cursor.fetchall()
    if not rows:
        logging.info(f"Таблица {table} пуста")
        return

    # Вставляем в новую таблицу
    insert_cols = ", ".join(f'"{col}"' for col in common_cols)
    placeholders = ", ".join(["?"] * len(common_cols))
    insert_sql = f"INSERT OR IGNORE INTO {table} ({insert_cols}) VALUES ({placeholders})"
    await new_conn.executemany(insert_sql, rows)
    await new_conn.commit()
    logging.info(f"Скопировано {len(rows)} записей в таблицу {table}")

async def migrate():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logging.info("Начинаем перенос данных...")

    async with aiosqlite.connect(OLD_DB_PATH) as old_conn:
        async with aiosqlite.connect(NEW_DB_PATH) as new_conn:
            # Отключаем проверку внешних ключей на время вставки
            await new_conn.execute("PRAGMA foreign_keys = OFF")
            await new_conn.commit()

            for table in TABLES:
                await copy_table(old_conn, new_conn, table)

            # Включаем обратно
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