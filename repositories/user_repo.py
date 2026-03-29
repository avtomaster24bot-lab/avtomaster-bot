from .base import BaseRepository
from models.user import User

class UserRepository(BaseRepository[User]):
    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        row = await self._fetch_one(
            "SELECT id, telegram_id, city, role, full_name, phone, display_name_choice, created_at FROM users WHERE telegram_id = ?",
            (telegram_id,)
        )
        if not row:
            return None
        return User(
            id=row[0], telegram_id=row[1], city=row[2], role=row[3],
            full_name=row[4], phone=row[5], display_name_choice=row[6], created_at=row[7]
        )

    async def create(self, user: User) -> int:
        cursor = await self._execute(
            "INSERT INTO users (telegram_id, city, role, full_name, phone, display_name_choice) VALUES (?, ?, ?, ?, ?, ?)",
            (user.telegram_id, user.city, user.role, user.full_name, user.phone, user.display_name_choice)
        )
        await self.conn.commit()
        return cursor.lastrowid

    async def update(self, user: User) -> None:
        await self._execute(
            "UPDATE users SET city=?, role=?, full_name=?, phone=?, display_name_choice=? WHERE telegram_id=?",
            (user.city, user.role, user.full_name, user.phone, user.display_name_choice, user.telegram_id)
        )
        await self.conn.commit()