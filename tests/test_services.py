import pytest
from services.user_service import UserService
from services.request_service import RequestService

@pytest.mark.asyncio
async def test_user_service_register_user(db_session):
    service = UserService(db_session)
    user_id = await service.register_user(telegram_id=123, full_name="Test")
    assert user_id is not None
    user = await service.get_user(123)
    assert user.full_name == "Test"
    assert user.role == "client"

@pytest.mark.asyncio
async def test_request_service_create_request(db_session):
    # Сначала добавляем пользователя
    user_service = UserService(db_session)
    await user_service.register_user(telegram_id=1, full_name="Client")
    # Создаём заявку
    service = RequestService(db_session)
    request_id = await service.create_request(
        user_id=1,
        req_type="sto",
        city="TestCity",
        description="Test description"
    )
    assert request_id is not None
    req = await service.request_repo.get_by_id(request_id)
    assert req.type == "sto"
    assert req.status == "new"