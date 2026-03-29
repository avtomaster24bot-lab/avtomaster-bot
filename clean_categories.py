import sqlite3

DB_PATH = "avtomaster.db"
CITY_NAME = "Талдыкорган"

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Получаем city_id
    cursor.execute("SELECT id FROM cities WHERE name = ?", (CITY_NAME,))
    row = cursor.fetchone()
    if not row:
        print(f"Город '{CITY_NAME}' не найден.")
        conn.close()
        return
    city_id = row[0]

    # Находим дубликаты категорий
    cursor.execute("""
        SELECT name, COUNT(*) FROM categories
        WHERE city_id = ?
        GROUP BY name
        HAVING COUNT(*) > 1
    """, (city_id,))
    duplicates = cursor.fetchall()
    if not duplicates:
        print("Дубликатов категорий не найдено.")
        conn.close()
        return

    print("Найдены дубликаты:")
    for name, count in duplicates:
        print(f"  {name}: {count} шт.")

    # Удаляем дубликаты, оставляя минимальный id
    # Сначала переназначаем связи в station_categories
    print("Переназначаем station_categories...")
    cursor.execute("""
        UPDATE station_categories
        SET category_id = (
            SELECT MIN(c2.id)
            FROM categories c2
            WHERE c2.name = (SELECT c3.name FROM categories c3 WHERE c3.id = station_categories.category_id)
              AND c2.city_id = ?
        )
        WHERE station_id IN (SELECT id FROM stations)
    """, (city_id,))
    conn.commit()

    # Удаляем дубликаты категорий
    print("Удаляем дубликаты категорий...")
    cursor.execute("""
        DELETE FROM categories
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM categories
            WHERE city_id = ?
            GROUP BY name
        )
    """, (city_id,))
    conn.commit()

    # Проверяем результат
    cursor.execute("""
        SELECT name, COUNT(*) FROM categories
        WHERE city_id = ?
        GROUP BY name
        HAVING COUNT(*) > 1
    """, (city_id,))
    remaining = cursor.fetchall()
    if not remaining:
        print("✅ Дубликаты успешно удалены.")
    else:
        print("⚠️ Остались дубликаты:", remaining)

    conn.close()

if __name__ == "__main__":
    main()