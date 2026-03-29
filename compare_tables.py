import sqlite3

OLD_DB = "old_avtomaster.db"
NEW_DB = "avtomaster.db"

def show_columns(db_path, table):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table})")
    cols = [col[1] for col in cursor.fetchall()]
    conn.close()
    return cols

def compare():
    tables = ["stations", "car_washes", "tow_trucks", "suppliers", "service_providers", "requests"]
    for table in tables:
        old_cols = show_columns(OLD_DB, table)
        new_cols = show_columns(NEW_DB, table)
        print(f"\n{table}:")
        print(f"  Старая: {old_cols}")
        print(f"  Новая:  {new_cols}")

if __name__ == "__main__":
    compare()