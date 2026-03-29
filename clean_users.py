import asyncio
import aiosqlite
from config import DATABASE_URL

async def clean():
    db_path = DATABASE_URL.replace("sqlite:///", "")
    async with aiosqlite.connect(db_path) as conn:
        # ID для удаления
        user_ids = [294241311, 290840324, 1547224465]
        placeholders = ','.join('?' for _ in user_ids)
        
        # Удаляем связанные данные
        await conn.execute(f"DELETE FROM reviews WHERE user_id IN ({placeholders})", user_ids)
        await conn.execute(f"DELETE FROM requests WHERE user_id IN ({placeholders})", user_ids)
        await conn.execute(f"DELETE FROM part_requests WHERE user_id IN ({placeholders})", user_ids)
        await conn.execute(f"DELETE FROM partner_requests WHERE user_id IN ({placeholders})", user_ids)
        await conn.execute(f"DELETE FROM user_cars WHERE user_id IN ({placeholders})", user_ids)
        await conn.execute(f"DELETE FROM service_records WHERE user_id IN ({placeholders})", user_ids)
        await conn.execute(f"DELETE FROM ai_chat_history WHERE user_id IN ({placeholders})", user_ids)
        
        # Удаляем записи, где пользователь был администратором (особенно для 1547224465)
        await conn.execute("DELETE FROM stations WHERE admin_id = ?", (1547224465,))
        await conn.execute("DELETE FROM car_washes WHERE admin_id = ?", (1547224465,))
        await conn.execute("DELETE FROM tow_trucks WHERE admin_id = ?", (1547224465,))
        await conn.execute("DELETE FROM suppliers WHERE admin_id = ?", (1547224465,))
        await conn.execute("DELETE FROM service_providers WHERE admin_id = ?", (1547224465,))
        
        # Удаляем самих пользователей
        await conn.execute(f"DELETE FROM users WHERE telegram_id IN ({placeholders})", user_ids)
        
        await conn.commit()
        print(f"✅ Очистка пользователей {user_ids} завершена.")

if __name__ == "__main__":
    asyncio.run(clean())