import pytest
from repositories.user_repo import UserRepository
from models.user import User

@pytest.mark.asyncio
async def test_user_repo_create_and_get(db_session):
    repo = UserRepository(db_session)
    user = User(telegram_id=123456, full_name="Test User", role="client")
    user_id = await repo.create(user)
    assert user_id is not None
    fetched = await repo.get_by_telegram_id(123456)
    assert fetched is not None
    assert fetched.full_name == "Test User"
    assert fetched.role == "client"

@pytest.mark.asyncio
async def test_user_repo_update(db_session):
    repo = UserRepository(db_session)
    user = User(telegram_id=123456, full_name="Test User", role="client")
    await repo.create(user)
    user.role = "regional_admin"
    await repo.update(user)
    fetched = await repo.get_by_telegram_id(123456)
    assert fetched.role == "regional_admin"