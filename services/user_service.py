from repositories.user_repo import UserRepository
from models.user import User

class UserService:
    def __init__(self, conn):
        self.user_repo = UserRepository(conn)

    async def register_user(self, telegram_id: int, full_name: str) -> int:
        user = User(telegram_id=telegram_id, full_name=full_name, role='client')
        return await self.user_repo.create(user)

    async def get_user(self, telegram_id: int) -> User | None:
        return await self.user_repo.get_by_telegram_id(telegram_id)

    async def update_user(self, user: User):
        await self.user_repo.update(user)