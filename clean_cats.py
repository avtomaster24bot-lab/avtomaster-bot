import sqlite3

def clean():
    conn = sqlite3.connect('avtomaster.db')
    cursor = conn.cursor()
    
    # Временно отключаем проверку внешних ключей
    cursor.execute("PRAGMA foreign_keys = OFF")
    cursor.execute("BEGIN TRANSACTION")
    
    # Обновляем ссылки в station_categories: заменяем дублирующиеся category_id на минимальный id для того же имени
    cursor.execute('''
        UPDATE station_categories
        SET category_id = (
            SELECT MIN(c2.id)
            FROM categories c2
            WHERE c2.name = (SELECT c3.name FROM categories c3 WHERE c3.id = station_categories.category_id)
              AND c2.city_id = (SELECT id FROM cities WHERE name = 'Талдыкорган')
        )
        WHERE station_id IN (SELECT id FROM stations)
    ''')
    
    # Удаляем дубли категорий
    cursor.execute('''
        DELETE FROM categories
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM categories
            WHERE city_id = (SELECT id FROM cities WHERE name = 'Талдыкорган')
            GROUP BY name
        )
    ''')
    
    # Удаляем дубли в station_categories (если остались)
    cursor.execute('''
        DELETE FROM station_categories
        WHERE rowid NOT IN (
            SELECT MIN(rowid)
            FROM station_categories
            GROUP BY station_id, category_id
        )
    ''')
    
    cursor.execute("COMMIT")
    cursor.execute("PRAGMA foreign_keys = ON")
    conn.close()
    print("Очистка завершена. Дубли удалены.")

if __name__ == "__main__":
    clean()