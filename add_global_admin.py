import asyncio
import aiosqlite

async def add_global():
    async with aiosqlite.connect("avtomaster.db") as conn:
        admin_id = 8075974958  # замени на свой ID
        # Обновим, если есть, иначе создадим
        await conn.execute("UPDATE users SET role = 'global_admin' WHERE telegram_id = ?", (admin_id,))
        cursor = await conn.execute("SELECT 1 FROM users WHERE telegram_id = ?", (admin_id,))
        if not await cursor.fetchone():
            await conn.execute(
                "INSERT INTO users (telegram_id, role, full_name) VALUES (?, 'global_admin', 'Главный Админ')",
                (admin_id,)
            )
        await conn.commit()
    print("Глобальный администратор добавлен")

asyncio.run(add_global())