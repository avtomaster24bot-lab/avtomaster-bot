import asyncio
import aiosqlite

async def add_regional():
    async with aiosqlite.connect("avtomaster.db") as conn:
        regional_id = 290840324  # из твоей старой базы
        await conn.execute(
            "UPDATE users SET role = 'regional_admin', city = 'Талдыкорган' WHERE telegram_id = ?",
            (regional_id,)
        )
        await conn.commit()
    print("Региональный администратор добавлен")

asyncio.run(add_regional())