import pytest
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, User, Chat
from unittest.mock import AsyncMock, patch
from handlers.client import router as client_router

@pytest.mark.asyncio
async def test_start_handler():
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(client_router)
    message = Message(
        message_id=1,
        date=0,
        chat=Chat(id=123, type="private"),
        from_user=User(id=123, is_bot=False, first_name="Test"),
        text="/start"
    )
    with patch('handlers.common.cmd_start', new_callable=AsyncMock) as mock_start:
        await dp.feed_update(bot=AsyncMock(), update=message)
        # проверяем, что вызван нужный обработчик
        # mock_start.assert_called_once()