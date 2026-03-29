import asyncio
import aiosqlite
from config import DATABASE_URL

async def add_test_data():
    db_path = DATABASE_URL.replace("sqlite:///", "")
    async with aiosqlite.connect(db_path) as conn:
        city_name = "Талдыкорган"  # укажите свой город, если нужно
        cursor = await conn.execute("SELECT id FROM cities WHERE name = ?", (city_name,))
        row = await cursor.fetchone()
        if not row:
            print(f"Город {city_name} не найден. Доступные города:")
            cursor = await conn.execute("SELECT name FROM cities")
            cities = await cursor.fetchall()
            for c in cities:
                print(f"  {c[0]}")
            return
        city_id = row[0]
        print(f"Город: {city_name} (ID={city_id})")

        # Категории
        categories = [
            ("Ремонт двигателя", city_id),
            ("Ремонт ходовой", city_id),
            ("Электрика", city_id),
            ("Кузовной ремонт", city_id),
        ]
        for name, cid in categories:
            await conn.execute("INSERT OR IGNORE INTO categories (name, city_id) VALUES (?, ?)", (name, cid))
        await conn.commit()
        print("Категории добавлены.")

        # Получаем ID категорий
        cursor = await conn.execute("SELECT id, name FROM categories WHERE city_id = ?", (city_id,))
        cats = {row[1]: row[0] for row in await cursor.fetchall()}
        print("ID категорий:", cats)

        # Подкатегории
        if "Ремонт двигателя" in cats:
            engine_id = cats["Ремонт двигателя"]
            subs = ["Капитальный ремонт", "Замена ГРМ", "Замена прокладки ГБЦ", "Диагностика двигателя"]
            for sub in subs:
                await conn.execute("INSERT OR IGNORE INTO subcategories (name, category_id) VALUES (?, ?)", (sub, engine_id))
            print("Подкатегории для двигателя добавлены.")

        if "Кузовной ремонт" in cats:
            body_id = cats["Кузовной ремонт"]
            subs = ["Ремонт бампера", "Покраска", "Рихтовка"]
            for sub in subs:
                await conn.execute("INSERT OR IGNORE INTO subcategories (name, category_id) VALUES (?, ?)", (sub, body_id))
            print("Подкатегории для кузовного ремонта добавлены.")

        await conn.commit()
        print("Тестовые данные добавлены.")

if __name__ == "__main__":
    asyncio.run(add_test_data())