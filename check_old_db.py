# check_old_db.py
import sqlite3

OLD_DB_PATH = "old_avtomaster.db"

conn = sqlite3.connect(OLD_DB_PATH)
cursor = conn.cursor()

# Список всех таблиц
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cursor.fetchall()

print("Таблицы в старой базе:")
for (table_name,) in tables:
    if table_name.startswith("sqlite_"):
        continue
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = cursor.fetchone()[0]
    print(f"  {table_name}: {count} записей")

conn.close()