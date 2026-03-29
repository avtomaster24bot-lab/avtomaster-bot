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
    print(f"Город: {CITY_NAME} (ID={city_id})")

    # 1. Удаляем все связи СТО с категориями (для всех СТО в этом городе)
    print("Удаляем все связи station_categories для СТО в этом городе...")
    cursor.execute("""
        DELETE FROM station_categories
        WHERE station_id IN (SELECT id FROM stations WHERE city_id = ?)
    """, (city_id,))
    print(f"Удалено строк из station_categories: {cursor.rowcount}")

    # 2. Теперь удаляем дубликаты категорий
    print("Удаляем дубликаты категорий...")
    # Находим ID категорий, которые нужно оставить (минимальный id для каждого имени)
    cursor.execute("""
        SELECT MIN(id) FROM categories
        WHERE city_id = ?
        GROUP BY name
    """, (city_id,))
    keep_ids = [row[0] for row in cursor.fetchall()]
    print(f"Будут оставлены ID: {keep_ids}")

    if keep_ids:
        # Удаляем все категории, кроме тех, что в keep_ids
        placeholders = ','.join('?' for _ in keep_ids)
        cursor.execute(f"""
            DELETE FROM categories
            WHERE city_id = ? AND id NOT IN ({placeholders})
        """, (city_id, *keep_ids))
        print(f"Удалено категорий: {cursor.rowcount}")
    else:
        print("Нет категорий для удаления.")

    conn.commit()
    conn.close()
    print("✅ Очистка завершена. Теперь запустите бота и заново добавьте категории через 'Управление категориями'.")

if __name__ == "__main__":
    main()