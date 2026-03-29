# view_db.py
import sqlite3
import sys

DB_PATH = "avtomaster.db"

def view_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Список всех таблиц
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = cursor.fetchall()
    
    print("=" * 60)
    print(f"База данных: {DB_PATH}")
    print("=" * 60)
    
    for (table_name,) in tables:
        # Пропускаем служебные таблицы
        if table_name.startswith("sqlite_"):
            continue
        
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        
        print(f"\n📊 Таблица: {table_name} ({count} записей)")
        
        if count > 0:
            # Выводим первые 3 строки
            cursor.execute(f"SELECT * FROM {table_name} LIMIT 3")
            rows = cursor.fetchall()
            # Получаем названия колонок
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [col[1] for col in cursor.fetchall()]
            print(f"   Колонки: {', '.join(columns)}")
            print("   Примеры данных:")
            for row in rows:
                # Ограничиваем длину вывода
                short_row = []
                for val in row:
                    if val is None:
                        short_row.append("NULL")
                    else:
                        s = str(val)
                        if len(s) > 50:
                            s = s[:47] + "..."
                        short_row.append(s)
                print(f"      {short_row}")
    
    conn.close()
    print("\n" + "=" * 60)
    print("Просмотр завершён.")

if __name__ == "__main__":
    view_db()