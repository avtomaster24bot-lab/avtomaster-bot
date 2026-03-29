# test_admins.py
import asyncio
from database import db
from repositories.user_repo import UserRepository

async def test():
    async with db.session() as conn:
        repo = UserRepository(conn)
        # Все пользователи с ролью regional_admin или global_admin
        rows = await repo._fetch_all("SELECT telegram_id, role, full_name FROM users WHERE role IN ('regional_admin', 'global_admin')")
        print(f"Найдено админов: {len(rows)}")
        for row in rows:
            print(f"  {row[0]} - {row[1]} - {row[2]}")

if __name__ == "__main__":
    asyncio.run(test())