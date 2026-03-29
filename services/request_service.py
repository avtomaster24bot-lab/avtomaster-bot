# services/request_service.py
import json
from datetime import datetime
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from repositories.request_repo import RequestRepository
from repositories.user_repo import UserRepository
from repositories.station_repo import StationRepository
from repositories.car_wash_repo import CarWashRepository
from repositories.tow_truck_repo import TowTruckRepository
from repositories.supplier_repo import SupplierRepository
from repositories.service_provider_repo import ServiceProviderRepository
from utils.helpers import notify_regional_admin
from utils.logger import logger

class RequestService:
    def __init__(self, conn):
        self.conn = conn
        self.request_repo = RequestRepository(conn)
        self.user_repo = UserRepository(conn)
        self.station_repo = StationRepository(conn)
        self.car_wash_repo = CarWashRepository(conn)
        self.tow_truck_repo = TowTruckRepository(conn)
        self.supplier_repo = SupplierRepository(conn)
        self.service_provider_repo = ServiceProviderRepository(conn)

    async def create_request(self, user_id: int, req_type: str, city: str,
                             description: str, **kwargs) -> int:
        data = {
            "user_id": user_id,
            "type": req_type,
            "city": city,
            "description": description,
            "status": "new",
            "created_at": datetime.now().isoformat()
        }
        data.update(kwargs)
        if "subcategories" in data and isinstance(data["subcategories"], list):
            data["subcategories"] = json.dumps(data["subcategories"])
        return await self.request_repo.create(data)

    async def accept_request(self, request_id: int, executor_id: int, executor_type: str) -> None:
        await self.request_repo.update(request_id, {
            "status": "accepted",
            "accepted_by": executor_id,
            "accepted_at": datetime.now().isoformat()
        })

    async def complete_request(self, request_id: int, total_amount: int) -> None:
        await self.request_repo.update(request_id, {
            "status": "completed",
            "completed_at": datetime.now().isoformat(),
            "total_amount": total_amount
        })

    async def notify_executors(self, request_id: int, req_type: str, city: str, bot):
        request = await self.request_repo.get_by_id(request_id)
        if not request:
            logger.error(f"Заявка {request_id} не найдена")
            return

        description = request.description
        user = await self.user_repo.get_by_telegram_id(request.user_id)
        client_phone = user.phone if user else "не указан"
        client_name = user.full_name if user else "не указан"
        client_info = f"{client_name} ({client_phone})"

        # 1. Уведомляем регионального администратора (только один раз)
        await notify_regional_admin(bot, city, f"Новая заявка #{request_id} ({req_type})\n{description[:200]}")

        # 2. Уведомляем исполнителей в зависимости от типа
        if req_type == 'sto':
            stations = await self.station_repo.get_by_city(city)
            for station in stations:
                try:
                    await bot.send_message(
                        station.admin_id,
                        f"🚗 Новая заявка #{request_id} на СТО\n"
                        f"Город: {city}\n"
                        f"Описание: {description}\n"
                        f"Клиент: {client_info}\n\n"
                        "Принять заявку можно в панели администрирования.",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_sto_{request_id}")]
                        ])
                    )
                except Exception as e:
                    logger.error(f"Не удалось уведомить СТО {station.admin_id}: {e}")

        elif req_type == 'wash':
            washes = await self.car_wash_repo.get_by_city(city)
            for wash in washes:
                try:
                    await bot.send_message(
                        wash.admin_id,
                        f"🚿 Новая заявка на мойку #{request_id}\n"
                        f"Город: {city}\n"
                        f"Описание: {description}\n"
                        f"Клиент: {client_info}\n\n"
                        "Принять заявку можно в панели администрирования.",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_wash_{request_id}")]
                        ])
                    )
                except Exception as e:
                    logger.error(f"Не удалось уведомить мойку {wash.admin_id}: {e}")

        elif req_type == 'tow':
            towers = await self.tow_truck_repo.get_by_city(city)
            for tower in towers:
                try:
                    await bot.send_message(
                        tower.admin_id,
                        f"🚨 Новая заявка на эвакуатор #{request_id}\n"
                        f"Город: {city}\n"
                        f"{description}\n\n"
                        "Предложите цену:",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="💰 Предложить цену", callback_data=f"tow_offer_{request_id}")]
                        ])
                    )
                except Exception as e:
                    logger.error(f"Не удалось уведомить эвакуатор {tower.admin_id}: {e}")

        elif req_type == 'urgent':
            service_subtype = request.service_subtype
            if service_subtype:
                providers = await self.service_provider_repo.get_by_city_and_type(city, service_subtype)
                for provider in providers:
                    try:
                        await bot.send_message(
                            provider.admin_id,
                            f"🆘 Новая заявка #{request_id} на услугу «{service_subtype}»\n"
                            f"Город: {city}\n"
                            f"{description}\n\n"
                            "Предложите цену:",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                [InlineKeyboardButton(text="💰 Предложить цену", callback_data=f"urgent_offer_{request_id}")]
                            ])
                        )
                    except Exception as e:
                        logger.error(f"Не удалось уведомить специалиста {provider.admin_id}: {e}")

        elif req_type == 'roadside':
            suppliers = await self.supplier_repo.get_by_city(city)
            for supplier in suppliers:
                try:
                    await bot.send_message(
                        supplier.admin_id,
                        f"🆘 Новая заявка на автопомощь #{request_id}\n"
                        f"Город: {city}\n"
                        f"{description}\n\n"
                        "Предложите цену:",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="💰 Предложить цену", callback_data=f"roadside_offer_{request_id}")]
                        ])
                    )
                except Exception as e:
                    logger.error(f"Не удалось уведомить поставщика {supplier.admin_id}: {e}")

        else:
            logger.warning(f"Неизвестный тип заявки для уведомления: {req_type}")