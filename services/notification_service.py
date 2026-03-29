# services/notification_service.py
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from utils.logger import logger

class NotificationService:
    """
    Сервис для отправки уведомлений пользователям и администраторам.
    Требует экземпляр Bot при инициализации.
    """
    def __init__(self, bot: Bot):
        self.bot = bot

    async def send_to_admin(self, admin_id: int, text: str, reply_markup: InlineKeyboardMarkup = None):
        """Отправляет сообщение администратору."""
        try:
            await self.bot.send_message(admin_id, text, reply_markup=reply_markup)
            logger.info(f"Уведомление отправлено админу {admin_id}")
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление админу {admin_id}: {e}")

    async def send_to_client(self, chat_id: int, text: str, reply_markup: InlineKeyboardMarkup = None):
        """Отправляет сообщение клиенту."""
        try:
            await self.bot.send_message(chat_id, text, reply_markup=reply_markup)
            logger.info(f"Уведомление отправлено клиенту {chat_id}")
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление клиенту {chat_id}: {e}")

    async def broadcast_to_role(self, role: str, text: str, reply_markup: InlineKeyboardMarkup = None):
        """
        Рассылает сообщение всем пользователям с указанной ролью.
        role: 'client', 'station_admin', 'wash_admin', 'tow_admin', 'supplier', 'service_provider', 'regional_admin', 'global_admin'
        """
        from database import db
        async with db.session() as conn:
            cursor = await conn.execute("SELECT telegram_id FROM users WHERE role = ?", (role,))
            users = await cursor.fetchall()
        for (user_id,) in users:
            await self.send_to_admin(user_id, text, reply_markup)
            # Небольшая задержка, чтобы не превысить лимиты Telegram
            import asyncio
            await asyncio.sleep(0.05)

    async def notify_new_request(self, request_id: int, request_type: str, city: str, description: str, client_info: str):
        """
        Универсальное уведомление о новой заявке для всех исполнителей в городе.
        """
        from repositories.station_repo import StationRepository
        from repositories.car_wash_repo import CarWashRepository
        from repositories.tow_truck_repo import TowTruckRepository
        from repositories.supplier_repo import SupplierRepository
        from repositories.service_provider_repo import ServiceProviderRepository
        from database import db

        async with db.session() as conn:
            if request_type == 'sto':
                repo = StationRepository(conn)
                entities = await repo.get_by_city(city)
                callback_prefix = "accept_sto"
                text_template = (
                    f"🚗 Новая заявка #{request_id} на СТО\n"
                    f"Город: {city}\n"
                    f"Описание: {description}\n"
                    f"Клиент: {client_info}\n\n"
                    "Принять заявку можно в панели администрирования."
                )
            elif request_type == 'wash':
                repo = CarWashRepository(conn)
                entities = await repo.get_by_city(city)
                callback_prefix = "accept_wash"
                text_template = (
                    f"🚿 Новая заявка на мойку #{request_id}\n"
                    f"Город: {city}\n"
                    f"Описание: {description}\n"
                    f"Клиент: {client_info}\n\n"
                    "Принять заявку можно в панели администрирования."
                )
            elif request_type == 'tow':
                repo = TowTruckRepository(conn)
                entities = await repo.get_by_city(city)
                callback_prefix = "tow_offer"
                text_template = (
                    f"🚨 Новая заявка на эвакуатор #{request_id}\n"
                    f"Город: {city}\n"
                    f"{description}\n\n"
                    "Предложите цену:"
                )
            elif request_type == 'urgent':
                # Для срочных услуг нужно передать service_subtype
                repo = ServiceProviderRepository(conn)
                # Здесь нужно знать service_subtype, поэтому лучше вызывать отдельно
                return
            else:
                return

            # Отправляем каждому исполнителю
            for entity in entities:
                admin_id = entity.admin_id
                if admin_id:
                    await self.send_to_admin(
                        admin_id,
                        text_template,
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="✅ Принять", callback_data=f"{callback_prefix}_{request_id}")]
                        ])
                    )