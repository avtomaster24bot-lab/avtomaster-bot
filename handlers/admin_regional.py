# handlers/admin_regional.py
import json
import logging
import os
import tempfile
from datetime import datetime
from aiogram import Router, F, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram import Bot

from database import db
from repositories.user_repo import UserRepository
from repositories.station_repo import StationRepository
from repositories.car_wash_repo import CarWashRepository
from repositories.tow_truck_repo import TowTruckRepository
from repositories.supplier_repo import SupplierRepository
from repositories.service_provider_repo import ServiceProviderRepository
from repositories.request_repo import RequestRepository
from repositories.review_repo import ReviewRepository
from states.admin_states import RegionalAdminStates
from keyboards.reply import main_menu_kb, back_kb
from keyboards.inline import partner_type_kb, supplier_type_kb, urgent_service_type_kb, yes_no_kb, confirm_request_kb
from utils.helpers import notify_regional_admin, get_city_id, generate_wash_slots, stars_from_rating
from handlers.station_admin import parse_and_insert_prices, manage_categories  # импортируем manage_categories

logger = logging.getLogger(__name__)
router = Router()


async def is_regional_admin(user_id: int) -> bool:
    async with db.session() as conn:
        cursor = await conn.execute("SELECT role, city FROM users WHERE telegram_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row and row[0] == 'regional_admin' and row[1] is not None


# ---------- Панель регионального админа ----------
@router.message(F.text == "🏙 Панель регионального админа")
async def regional_panel(message: Message, state: FSMContext):
    if not await is_regional_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    kb = types.ReplyKeyboardMarkup(keyboard=[
        [types.KeyboardButton(text="➕ Добавить СТО")],
        [types.KeyboardButton(text="➕ Добавить мойку")],
        [types.KeyboardButton(text="➕ Добавить эвакуатор")],
        [types.KeyboardButton(text="➕ Добавить поставщика")],
        [types.KeyboardButton(text="➕ Добавить специалиста срочных услуг")],
        [types.KeyboardButton(text="📋 Управление приоритетами СТО")],
        [types.KeyboardButton(text="⭐ Модерация отзывов")],
        [types.KeyboardButton(text="📊 Статистика по городу")],
        [types.KeyboardButton(text="📋 Заявки на услуги")],
        [types.KeyboardButton(text="📋 Запросы запчастей")],
        [types.KeyboardButton(text="📤 Загрузить прайс для СТО")],
        [types.KeyboardButton(text="⬅ Главное меню")]
    ], resize_keyboard=True)
    await message.answer("Панель регионального администратора", reply_markup=kb)


# ---------- Просмотр списка СТО в городе ----------
@router.message(F.text == "📋 Список СТО")
async def list_stations(message: Message, state: FSMContext):
    if not await is_regional_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    user_id = message.from_user.id
    async with db.session() as conn:
        cursor = await conn.execute("SELECT city FROM users WHERE telegram_id = ?", (user_id,))
        row = await cursor.fetchone()
        if not row or not row[0]:
            await message.answer("Ваш город не определён.")
            return
        city = row[0]
        city_id = await get_city_id(city)
        if not city_id:
            await message.answer("Город не найден в справочнике.")
            return
        station_repo = StationRepository(conn)
        stations = await station_repo.get_by_city(city)  # нужен метод get_by_city в StationRepository
        if not stations:
            await message.answer("В вашем городе нет зарегистрированных СТО.")
            return
        text = f"📋 Список СТО в городе {city}:\n\n"
        for idx, s in enumerate(stations, 1):
            rating_stars = stars_from_rating(s.rating or 0)
            text += f"{idx}. {s.name}\n"
            text += f"   📞 {s.phone or 'не указан'}\n"
            text += f"   📍 {s.address or 'адрес не указан'}\n"
            text += f"   🎯 Приоритет: {s.priority}\n"
            text += f"   {rating_stars}\n\n"
        await message.answer(text)


# ---------- Просмотр списка поставщиков ----------
@router.message(F.text == "📋 Список поставщиков")
async def list_suppliers(message: Message, state: FSMContext):
    if not await is_regional_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    user_id = message.from_user.id
    async with db.session() as conn:
        cursor = await conn.execute("SELECT city FROM users WHERE telegram_id = ?", (user_id,))
        row = await cursor.fetchone()
        if not row or not row[0]:
            await message.answer("Ваш город не определён.")
            return
        city = row[0]
        city_id = await get_city_id(city)
        if not city_id:
            await message.answer("Город не найден в справочнике.")
            return
        supplier_repo = SupplierRepository(conn)
        suppliers = await supplier_repo.get_by_city(city)  # нужен метод get_by_city
        if not suppliers:
            await message.answer("В вашем городе нет зарегистрированных поставщиков.")
            return
        type_names = {'shop':'🏪 Магазин', 'dismantler':'🔧 Разборка', 'installer':'🔨 Установщик'}
        grouped = {}
        for s in suppliers:
            grouped.setdefault(s.type, []).append(s)
        text = f"📦 Список поставщиков в городе {city}:\n\n"
        for typ, items in grouped.items():
            text += f"{type_names.get(typ, typ)}:\n"
            for s in items:
                rating_stars = stars_from_rating(s.rating or 0)
                text += f"   • {s.name}\n"
                text += f"     📞 {s.phone or 'не указан'}\n"
                text += f"     📍 {s.address or 'адрес не указан'}\n"
                text += f"     {rating_stars}\n\n"
        await message.answer(text)


# ---------- Просмотр списка эвакуаторов ----------
@router.message(F.text == "📋 Список эвакуаторов")
async def list_tow_trucks(message: Message, state: FSMContext):
    if not await is_regional_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    user_id = message.from_user.id
    async with db.session() as conn:
        cursor = await conn.execute("SELECT city FROM users WHERE telegram_id = ?", (user_id,))
        row = await cursor.fetchone()
        if not row or not row[0]:
            await message.answer("Ваш город не определён.")
            return
        city = row[0]
        city_id = await get_city_id(city)
        if not city_id:
            await message.answer("Город не найден в справочнике.")
            return
        tow_repo = TowTruckRepository(conn)
        towers = await tow_repo.get_by_city(city)  # нужен метод get_by_city
        if not towers:
            await message.answer("В вашем городе нет зарегистрированных эвакуаторов.")
            return
        text = f"🚨 Список эвакуаторов в городе {city}:\n\n"
        for idx, t in enumerate(towers, 1):
            rating_stars = stars_from_rating(t.rating or 0)
            text += f"{idx}. {t.name}\n"
            text += f"   📞 {t.phone or 'не указан'}\n"
            text += f"   📍 {t.address or 'адрес не указан'}\n"
            text += f"   {rating_stars}\n\n"
        await message.answer(text)


# ---------- Добавление СТО ----------
@router.message(F.text == "➕ Добавить СТО")
async def add_station_start(message: Message, state: FSMContext):
    if not await is_regional_admin(message.from_user.id):
        return
    await state.set_state(RegionalAdminStates.adding_station_name)
    await message.answer("Введите название СТО:")


@router.message(StateFilter(RegionalAdminStates.adding_station_name))
async def add_station_name(message: Message, state: FSMContext):
    name = message.text
    await state.update_data(name=name)
    await state.set_state(RegionalAdminStates.adding_station_address)
    await message.answer("Введите адрес СТО:")


@router.message(StateFilter(RegionalAdminStates.adding_station_address))
async def add_station_address(message: Message, state: FSMContext):
    address = message.text
    await state.update_data(address=address)
    await state.set_state(RegionalAdminStates.adding_station_phone)
    await message.answer("Введите телефон СТО:")


@router.message(StateFilter(RegionalAdminStates.adding_station_phone))
async def add_station_phone(message: Message, state: FSMContext):
    phone = message.text
    await state.update_data(phone=phone)
    await state.set_state(RegionalAdminStates.adding_station_admin)
    await message.answer("Введите Telegram ID администратора СТО (число):")


@router.message(StateFilter(RegionalAdminStates.adding_station_admin))
async def add_station_admin(message: Message, state: FSMContext):
    try:
        admin_id = int(message.text)
    except ValueError:
        await message.answer("Введите корректный ID.")
        return
    data = await state.get_data()
    user_id = message.from_user.id
    async with db.session() as conn:
        cursor = await conn.execute("SELECT city FROM users WHERE telegram_id = ?", (user_id,))
        city_name = await cursor.fetchone()
        if not city_name:
            await message.answer("Город не определён.")
            return
        city_name = city_name[0]
        city_id = await get_city_id(city_name)
        if not city_id:
            await message.answer("Город не найден в справочнике.")
            return
        station_repo = StationRepository(conn)
        station_id = await station_repo.create({
            "name": data['name'],
            "city_id": city_id,
            "admin_id": admin_id,
            "phone": data['phone'],
            "address": data['address'],
            "priority": 0,
            "is_premium": False
        })
        await conn.execute("UPDATE users SET role = 'station_admin' WHERE telegram_id = ?", (admin_id,))
        await conn.commit()
    # После создания СТО предлагаем перейти к управлению категориями
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛠 Управление категориями", callback_data=f"manage_cats_{station_id}")]
    ])
    await message.answer(f"СТО добавлено. ID: {station_id}", reply_markup=kb)
    await state.clear()


# ---------- Обработчик перехода к управлению категориями для нового СТО ----------
@router.callback_query(F.data.startswith("manage_cats_"))
async def redirect_to_categories(callback: CallbackQuery, state: FSMContext):
    station_id = int(callback.data.split("_")[2])
    # Устанавливаем station_id в состояние и вызываем обработчик manage_categories
    await state.update_data(station_id=station_id)
    await callback.message.answer("Переход к управлению категориями...")
    # Вызываем функцию manage_categories из station_admin.py
    from handlers.station_admin import manage_categories
    await manage_categories(callback.message, state)
    await callback.answer()


# ---------- Добавление мойки ----------
@router.message(F.text == "➕ Добавить мойку")
async def add_wash_start(message: Message, state: FSMContext):
    if not await is_regional_admin(message.from_user.id):
        return
    await state.set_state(RegionalAdminStates.adding_wash_name)
    await message.answer("Введите название автомойки:")


@router.message(StateFilter(RegionalAdminStates.adding_wash_name))
async def add_wash_name(message: Message, state: FSMContext):
    name = message.text
    await state.update_data(name=name)
    await state.set_state(RegionalAdminStates.adding_wash_address)
    await message.answer("Введите адрес мойки:")


@router.message(StateFilter(RegionalAdminStates.adding_wash_address))
async def add_wash_address(message: Message, state: FSMContext):
    address = message.text
    await state.update_data(address=address)
    await state.set_state(RegionalAdminStates.adding_wash_phone)
    await message.answer("Введите телефон мойки:")


@router.message(StateFilter(RegionalAdminStates.adding_wash_phone))
async def add_wash_phone(message: Message, state: FSMContext):
    phone = message.text
    await state.update_data(phone=phone)
    await state.set_state(RegionalAdminStates.adding_wash_boxes)
    await message.answer("Введите количество боксов:")


@router.message(StateFilter(RegionalAdminStates.adding_wash_boxes))
async def add_wash_boxes(message: Message, state: FSMContext):
    try:
        boxes = int(message.text)
    except ValueError:
        await message.answer("Введите число.")
        return
    await state.update_data(boxes=boxes)
    await state.set_state(RegionalAdminStates.adding_wash_duration)
    await message.answer("Введите длительность услуги в минутах:")


@router.message(StateFilter(RegionalAdminStates.adding_wash_duration))
async def add_wash_duration(message: Message, state: FSMContext):
    try:
        duration = int(message.text)
    except ValueError:
        await message.answer("Введите число.")
        return
    await state.update_data(duration=duration)
    await state.set_state(RegionalAdminStates.adding_wash_admin)
    await message.answer("Введите Telegram ID администратора мойки (число):")


@router.message(StateFilter(RegionalAdminStates.adding_wash_admin))
async def add_wash_admin(message: Message, state: FSMContext):
    try:
        admin_id = int(message.text)
    except ValueError:
        await message.answer("Введите корректный ID.")
        return
    data = await state.get_data()
    user_id = message.from_user.id
    async with db.session() as conn:
        cursor = await conn.execute("SELECT city FROM users WHERE telegram_id = ?", (user_id,))
        city_name = await cursor.fetchone()
        if not city_name:
            await message.answer("Город не определён.")
            return
        city_name = city_name[0]
        city_id = await get_city_id(city_name)
        if not city_id:
            await message.answer("Город не найден в справочнике.")
            return
        wash_repo = CarWashRepository(conn)
        wash_id = await wash_repo.create({
            "name": data['name'],
            "city_id": city_id,
            "admin_id": admin_id,
            "phone": data['phone'],
            "address": data['address'],
            "boxes": data['boxes'],
            "duration": data['duration'],
            "working_hours": None,
            "slot_duration": 30,
            "break_duration": 5,
            "work_start": "09:00",
            "work_end": "21:00",
            "days_off": "[]"
        })
        await conn.execute("UPDATE users SET role = 'wash_admin' WHERE telegram_id = ?", (admin_id,))
        await conn.commit()
    await message.answer(f"Мойка добавлена. ID: {wash_id}")
    await state.clear()


# ---------- Добавление эвакуатора ----------
@router.message(F.text == "➕ Добавить эвакуатор")
async def add_tow_start(message: Message, state: FSMContext):
    if not await is_regional_admin(message.from_user.id):
        return
    await state.set_state(RegionalAdminStates.adding_tow_name)
    await message.answer("Введите название эвакуатора:")


@router.message(StateFilter(RegionalAdminStates.adding_tow_name))
async def add_tow_name(message: Message, state: FSMContext):
    name = message.text
    await state.update_data(name=name)
    await state.set_state(RegionalAdminStates.adding_tow_phone)
    await message.answer("Введите телефон эвакуатора:")


@router.message(StateFilter(RegionalAdminStates.adding_tow_phone))
async def add_tow_phone(message: Message, state: FSMContext):
    phone = message.text
    await state.update_data(phone=phone)
    await state.set_state(RegionalAdminStates.adding_tow_admin)
    await message.answer("Введите Telegram ID администратора эвакуатора (число):")


@router.message(StateFilter(RegionalAdminStates.adding_tow_admin))
async def add_tow_admin(message: Message, state: FSMContext):
    try:
        admin_id = int(message.text)
    except ValueError:
        await message.answer("Введите корректный ID.")
        return
    data = await state.get_data()
    user_id = message.from_user.id
    async with db.session() as conn:
        cursor = await conn.execute("SELECT city FROM users WHERE telegram_id = ?", (user_id,))
        city_name = await cursor.fetchone()
        if not city_name:
            await message.answer("Город не определён.")
            return
        city_name = city_name[0]
        city_id = await get_city_id(city_name)
        if not city_id:
            await message.answer("Город не найден в справочнике.")
            return
        tow_repo = TowTruckRepository(conn)
        tow_id = await tow_repo.create({
            "name": data['name'],
            "city_id": city_id,
            "admin_id": admin_id,
            "phone": data['phone'],
            "address": ""
        })
        await conn.execute("UPDATE users SET role = 'tow_admin' WHERE telegram_id = ?", (admin_id,))
        await conn.commit()
    await message.answer(f"Эвакуатор добавлен. ID: {tow_id}")
    await state.clear()


# ---------- Добавление поставщика с геолокацией ----------
@router.message(F.text == "➕ Добавить поставщика")
async def add_supplier_start(message: Message, state: FSMContext):
    if not await is_regional_admin(message.from_user.id):
        return
    await state.set_state(RegionalAdminStates.adding_supplier_name)
    await message.answer("Введите название поставщика (магазин/разборка):")


@router.message(StateFilter(RegionalAdminStates.adding_supplier_name))
async def add_supplier_name(message: Message, state: FSMContext):
    name = message.text
    await state.update_data(name=name)
    await state.set_state(RegionalAdminStates.adding_supplier_type)
    kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="🏪 Магазин (новые запчасти)")],
            [types.KeyboardButton(text="🔧 Разборка (б/у запчасти)")],
            [types.KeyboardButton(text="🛠 Установщик (услуги + запчасти)")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer("Выберите тип поставщика:", reply_markup=kb)


@router.message(StateFilter(RegionalAdminStates.adding_supplier_type))
async def add_supplier_type(message: Message, state: FSMContext):
    type_map = {
        "🏪 Магазин (новые запчасти)": "shop",
        "🔧 Разборка (б/у запчасти)": "dismantler",
        "🛠 Установщик (услуги + запчасти)": "installer"
    }
    if message.text not in type_map:
        await message.answer("Пожалуйста, выберите тип из кнопок.")
        return
    supplier_type = type_map[message.text]
    await state.update_data(supplier_type=supplier_type)
    await state.set_state(RegionalAdminStates.adding_supplier_address)
    await message.answer("Введите адрес поставщика:", reply_markup=back_kb())


@router.message(StateFilter(RegionalAdminStates.adding_supplier_address))
async def add_supplier_address(message: Message, state: FSMContext):
    address = message.text
    await state.update_data(address=address)
    await state.set_state(RegionalAdminStates.adding_supplier_phone)
    await message.answer("Введите телефон поставщика:")


@router.message(StateFilter(RegionalAdminStates.adding_supplier_phone))
async def add_supplier_phone(message: Message, state: FSMContext):
    phone = message.text
    await state.update_data(phone=phone)
    await state.set_state(RegionalAdminStates.adding_supplier_location)
    kb = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text="📍 Отправить геолокацию", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer(
        "Теперь укажите местоположение поставщика на карте.\n"
        "Это нужно для поиска «Рядом со мной». Отправьте геолокацию:",
        reply_markup=kb
    )


@router.message(StateFilter(RegionalAdminStates.adding_supplier_location), F.location)
async def add_supplier_location(message: Message, state: FSMContext):
    lat = message.location.latitude
    lon = message.location.longitude
    await state.update_data(lat=lat, lon=lon)
    await state.set_state(RegionalAdminStates.adding_supplier_admin)
    await message.answer(
        "Введите Telegram ID администратора поставщика (число):",
        reply_markup=back_kb()
    )


@router.message(StateFilter(RegionalAdminStates.adding_supplier_admin))
async def add_supplier_admin(message: Message, state: FSMContext):
    try:
        admin_id = int(message.text)
    except ValueError:
        await message.answer("Введите корректный числовой ID.")
        return
    data = await state.get_data()
    user_id = message.from_user.id
    async with db.session() as conn:
        cursor = await conn.execute("SELECT city FROM users WHERE telegram_id = ?", (user_id,))
        city_name = await cursor.fetchone()
        if not city_name:
            await message.answer("Город не определён.")
            return
        city_name = city_name[0]
        city_id = await get_city_id(city_name)
        if not city_id:
            await message.answer("Город не найден в справочнике.")
            return
        supplier_repo = SupplierRepository(conn)
        supplier_id = await supplier_repo.create({
            "name": data['name'],
            "type": data['supplier_type'],
            "city_id": city_id,
            "admin_id": admin_id,
            "phone": data['phone'],
            "address": data['address'],
            "latitude": data['lat'],
            "longitude": data['lon'],
            "work_hours": None,
            "delivery_available": False
        })
        await conn.execute("UPDATE users SET role = 'supplier' WHERE telegram_id = ?", (admin_id,))
        await conn.commit()
    await message.answer(f"✅ Поставщик добавлен. ID: {supplier_id}")
    await state.clear()


# ---------- Добавление специалиста срочных услуг ----------
@router.message(F.text == "➕ Добавить специалиста срочных услуг")
async def add_urgent_specialist_start(message: Message, state: FSMContext):
    if not await is_regional_admin(message.from_user.id):
        return
    await state.set_state(RegionalAdminStates.adding_urgent_name)
    await message.answer("Введите имя или название организации специалиста:")


@router.message(StateFilter(RegionalAdminStates.adding_urgent_name))
async def add_urgent_name(message: Message, state: FSMContext):
    name = message.text
    await state.update_data(name=name)
    await state.set_state(RegionalAdminStates.adding_urgent_service_type)
    await message.answer(
        "Выберите тип срочной услуги:",
        reply_markup=urgent_service_type_kb()
    )


@router.callback_query(StateFilter(RegionalAdminStates.adding_urgent_service_type), F.data.startswith("urgent_type:"))
async def add_urgent_service_type(callback: CallbackQuery, state: FSMContext):
    service_type = callback.data.split(":")[1]
    await state.update_data(service_type=service_type)
    await state.set_state(RegionalAdminStates.adding_urgent_phone)
    await callback.message.edit_text("Введите телефон специалиста:")
    await callback.answer()


@router.message(StateFilter(RegionalAdminStates.adding_urgent_phone))
async def add_urgent_phone(message: Message, state: FSMContext):
    phone = message.text
    await state.update_data(phone=phone)
    await state.set_state(RegionalAdminStates.adding_urgent_address)
    await message.answer("Введите адрес (можно пропустить, отправьте /skip):", reply_markup=back_kb())


@router.message(StateFilter(RegionalAdminStates.adding_urgent_address))
async def add_urgent_address(message: Message, state: FSMContext):
    address = message.text if message.text != "/skip" else None
    await state.update_data(address=address)
    await state.set_state(RegionalAdminStates.adding_urgent_admin)
    await message.answer("Введите Telegram ID администратора (число):")


@router.message(StateFilter(RegionalAdminStates.adding_urgent_admin))
async def add_urgent_admin(message: Message, state: FSMContext):
    try:
        admin_id = int(message.text)
    except ValueError:
        await message.answer("Введите корректный числовой ID.")
        return
    data = await state.get_data()
    user_id = message.from_user.id
    async with db.session() as conn:
        cursor = await conn.execute("SELECT city FROM users WHERE telegram_id = ?", (user_id,))
        city_name = await cursor.fetchone()
        if not city_name:
            await message.answer("Город не определён.")
            return
        city_name = city_name[0]
        city_id = await get_city_id(city_name)
        if not city_id:
            await message.answer("Город не найден в справочнике.")
            return
        provider_repo = ServiceProviderRepository(conn)
        provider_id = await provider_repo.create({
            "service_type": data['service_type'],
            "name": data['name'],
            "city_id": city_id,
            "admin_id": admin_id,
            "phone": data['phone'],
            "address": data.get('address')
        })
        await conn.execute("UPDATE users SET role = 'service_provider' WHERE telegram_id = ?", (admin_id,))
        await conn.commit()
    await message.answer(f"✅ Специалист добавлен. ID: {provider_id}")
    await state.clear()


# ---------- Модерация отзывов ----------
@router.message(F.text == "⭐ Модерация отзывов")
async def moderate_reviews(message: Message, state: FSMContext):
    if not await is_regional_admin(message.from_user.id):
        return
    user_id = message.from_user.id
    async with db.session() as conn:
        cursor = await conn.execute("SELECT city FROM users WHERE telegram_id = ?", (user_id,))
        row = await cursor.fetchone()
        if not row or not row[0]:
            await message.answer("Ваш город не определён.")
            return
        admin_city = row[0]

        review_repo = ReviewRepository(conn)
        unmoderated = await review_repo.get_unmoderated(admin_city)  # нужно добавить метод
        if not unmoderated:
            await message.answer("Нет отзывов для модерации в вашем городе.")
            return

        for rev in unmoderated:
            rev_id, etype, eid, rating, comment, user_tg, user_name = rev
            # Получаем название объекта
            name = "неизвестно"
            if etype in ('station', 'sto'):
                cur = await conn.execute("SELECT name FROM stations WHERE id = ?", (eid,))
                row = await cur.fetchone()
                if row:
                    name = row[0]
            elif etype == 'car_wash':
                cur = await conn.execute("SELECT name FROM car_washes WHERE id = ?", (eid,))
                row = await cur.fetchone()
                if row:
                    name = row[0]
            elif etype == 'tow_truck':
                cur = await conn.execute("SELECT name FROM tow_trucks WHERE id = ?", (eid,))
                row = await cur.fetchone()
                if row:
                    name = row[0]
            elif etype == 'supplier':
                cur = await conn.execute("SELECT name FROM suppliers WHERE id = ?", (eid,))
                row = await cur.fetchone()
                if row:
                    name = row[0]
            elif etype == 'service_provider':
                cur = await conn.execute("SELECT name FROM service_providers WHERE id = ?", (eid,))
                row = await cur.fetchone()
                if row:
                    name = row[0]

            comment_display = comment if comment else "(нет комментария)"
            text = (f"⭐ Отзыв #{rev_id}\n"
                    f"Объект: {name} ({etype})\n"
                    f"Оценка: {rating}\n"
                    f"Автор: {user_name or 'Пользователь'}\n"
                    f"Комментарий: {comment_display}\n\n"
                    f"Действия:")
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Опубликовать", callback_data=f"mod_approve_{rev_id}")],
                [InlineKeyboardButton(text="❌ Скрыть", callback_data=f"mod_hide_{rev_id}")]
            ])
            await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("mod_approve_"))
async def approve_review(callback: CallbackQuery):
    if not await is_regional_admin(callback.from_user.id):
        await callback.answer("Нет прав")
        return
    rev_id = int(callback.data.split("_")[2])
    async with db.session() as conn:
        review_repo = ReviewRepository(conn)
        await review_repo.moderate(rev_id, approve=True)
    await callback.message.edit_text("✅ Отзыв опубликован, рейтинг обновлён.")
    await callback.answer()


@router.callback_query(F.data.startswith("mod_hide_"))
async def hide_review(callback: CallbackQuery):
    if not await is_regional_admin(callback.from_user.id):
        await callback.answer("Нет прав")
        return
    rev_id = int(callback.data.split("_")[2])
    async with db.session() as conn:
        review_repo = ReviewRepository(conn)
        await review_repo.moderate(rev_id, approve=False)
    await callback.message.edit_text("❌ Отзыв скрыт.")
    await callback.answer()


# ---------- Просмотр заявок в городе ----------
@router.message(F.text == "📋 Заявки на услуги")
async def list_service_requests(message: Message, state: FSMContext):
    if not await is_regional_admin(message.from_user.id):
        return
    user_id = message.from_user.id
    async with db.session() as conn:
        cursor = await conn.execute("SELECT city FROM users WHERE telegram_id = ?", (user_id,))
        row = await cursor.fetchone()
        if not row or not row[0]:
            await message.answer("Ваш город не определён.")
            return
        city = row[0]

        cursor = await conn.execute("""
            SELECT id, type, description, created_at, user_id
            FROM requests
            WHERE city = ? AND status = 'new'
            ORDER BY created_at DESC
            LIMIT 50
        """, (city,))
        requests = await cursor.fetchall()

    if not requests:
        await message.answer("В вашем городе нет новых заявок.")
        return

    text = "📋 *Новые заявки в вашем городе:*\n\n"
    for req in requests:
        req_id, req_type, desc, created_at, user_id = req
        type_emoji = {
            'sto': '🔧',
            'wash': '🚿',
            'tow': '🚨',
            'roadside': '🆘',
            'urgent': '🆘'
        }.get(req_type, '📌')
        short_desc = desc[:50] + "..." if len(desc) > 50 else desc
        try:
            dt = datetime.fromisoformat(created_at)
            date_str = dt.strftime("%d.%m %H:%M")
        except (ValueError, TypeError):
            date_str = created_at[:16]
        text += f"{type_emoji} #{req_id} от {date_str}\n_{short_desc}_\n\n"

    await message.answer(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Ввести номер заявки для просмотра", callback_data="regional_enter_request_id")]
        ])
    )


@router.callback_query(F.data == "regional_enter_request_id")
async def regional_enter_request_id(callback: CallbackQuery, state: FSMContext):
    await state.set_state(RegionalAdminStates.viewing_request)
    await callback.message.answer("Введите номер заявки, которую хотите просмотреть:")
    await callback.answer()


@router.message(StateFilter(RegionalAdminStates.viewing_request))
async def regional_view_request(message: Message, state: FSMContext):
    try:
        req_id = int(message.text)
    except ValueError:
        await message.answer("Пожалуйста, введите число.")
        return

    user_id = message.from_user.id
    async with db.session() as conn:
        cursor = await conn.execute("""
            SELECT r.*, u.phone, u.full_name
            FROM requests r
            JOIN users u ON r.user_id = u.telegram_id
            WHERE r.id = ? AND r.city = (SELECT city FROM users WHERE telegram_id = ?)
        """, (req_id, user_id))
        row = await cursor.fetchone()
        if not row:
            await message.answer("Заявка не найдена или не в вашем городе.")
            await state.clear()
            return
        # Преобразуем в словарь
        cols = [desc[0] for desc in cursor.description]
        req_data = dict(zip(cols, row))

    text = (
        f"📋 *Заявка #{req_data['id']}*\n"
        f"Тип: {req_data['type']}\n"
        f"Клиент: {req_data['full_name'] or 'не указан'} (📞 {req_data['phone'] or 'не указан'})\n"
        f"Город: {req_data['city']}\n"
        f"Дата: {req_data['created_at']}\n"
        f"Статус: {req_data['status']}\n\n"
        f"*Описание:*\n{req_data['description']}"
    )
    await message.answer(text, parse_mode='Markdown')
    await state.clear()


# ---------- Запросы запчастей ----------
@router.message(F.text == "📋 Запросы запчастей")
async def list_part_requests(message: Message, state: FSMContext):
    if not await is_regional_admin(message.from_user.id):
        return
    user_id = message.from_user.id
    async with db.session() as conn:
        cursor = await conn.execute("SELECT city FROM users WHERE telegram_id = ?", (user_id,))
        row = await cursor.fetchone()
        if not row or not row[0]:
            await message.answer("Ваш город не определён.")
            return
        city = row[0]

        cursor = await conn.execute("""
            SELECT id, part_name, car_info, comment, created_at, status
            FROM part_requests
            WHERE city = ? AND status = 'new'
            ORDER BY created_at DESC
            LIMIT 20
        """, (city,))
        requests = await cursor.fetchall()

    if not requests:
        await message.answer("В вашем городе нет новых запросов запчастей.")
        return

    text = "📦 *Новые запросы запчастей:*\n\n"
    for req in requests:
        req_id, part_name, car_info, comment, created_at, status = req
        try:
            date_str = datetime.fromisoformat(created_at.replace(' ', 'T')).strftime("%d.%m %H:%M")
        except Exception:
            date_str = created_at[:16]
        text += f"#{req_id} от {date_str}\n"
        text += f"Деталь: {part_name}\n"
        if car_info:
            text += f"Авто: {car_info}\n"
        if comment:
            text += f"Комментарий: {comment}\n"
        text += "\n"
    await message.answer(text, parse_mode='Markdown')


# ---------- Статистика по городу ----------
@router.message(F.text == "📊 Статистика по городу")
async def city_statistics(message: Message, state: FSMContext):
    if not await is_regional_admin(message.from_user.id):
        return
    user_id = message.from_user.id
    async with db.session() as conn:
        cursor = await conn.execute("SELECT city FROM users WHERE telegram_id = ?", (user_id,))
        row = await cursor.fetchone()
        if not row or not row[0]:
            await message.answer("Ваш город не определён.")
            return
        city = row[0]

        # Количество пользователей в городе
        cursor = await conn.execute("SELECT COUNT(*) FROM users WHERE city = ?", (city,))
        row = await cursor.fetchone()
        users_count = row[0] if row else 0

        # Количество СТО
        cur_stations = await conn.execute("SELECT COUNT(*) FROM stations WHERE city_id = (SELECT id FROM cities WHERE name = ?)", (city,))
        stations_row = await cur_stations.fetchone()
        stations_count = stations_row[0] if stations_row else 0

        # Количество моек
        cur_washes = await conn.execute("SELECT COUNT(*) FROM car_washes WHERE city_id = (SELECT id FROM cities WHERE name = ?)", (city,))
        washes_row = await cur_washes.fetchone()
        washes_count = washes_row[0] if washes_row else 0

        # Количество эвакуаторов
        cur_tows = await conn.execute("SELECT COUNT(*) FROM tow_trucks WHERE city_id = (SELECT id FROM cities WHERE name = ?)", (city,))
        tows_row = await cur_tows.fetchone()
        tows_count = tows_row[0] if tows_row else 0

        # Количество поставщиков
        cur_suppliers = await conn.execute("SELECT COUNT(*) FROM suppliers WHERE city_id = (SELECT id FROM cities WHERE name = ?)", (city,))
        suppliers_row = await cur_suppliers.fetchone()
        suppliers_count = suppliers_row[0] if suppliers_row else 0

        # Количество специалистов срочных услуг
        cur_providers = await conn.execute("SELECT COUNT(*) FROM service_providers WHERE city_id = (SELECT id FROM cities WHERE name = ?)", (city,))
        providers_row = await cur_providers.fetchone()
        providers_count = providers_row[0] if providers_row else 0

        # Количество заявок за последние 7 дней
        cur_requests = await conn.execute("SELECT COUNT(*) FROM requests WHERE city = ? AND created_at > datetime('now', '-7 days')", (city,))
        requests_row = await cur_requests.fetchone()
        requests_week = requests_row[0] if requests_row else 0

    text = (
        f"📊 *Статистика по городу {city}:*\n\n"
        f"👥 Пользователей: {users_count}\n"
        f"🔧 СТО: {stations_count}\n"
        f"🚿 Моек: {washes_count}\n"
        f"🚨 Эвакуаторов: {tows_count}\n"
        f"📦 Поставщиков: {suppliers_count}\n"
        f"🆘 Специалистов срочных услуг: {providers_count}\n"
        f"📋 Заявок за 7 дней: {requests_week}"
    )
    await message.answer(text, parse_mode='Markdown')


# ---------- Загрузка прайс-листа для СТО ----------
@router.message(F.text == "📤 Загрузить прайс для СТО")
async def upload_price_for_station_start(message: Message, state: FSMContext):
    if not await is_regional_admin(message.from_user.id):
        return
    user_id = message.from_user.id
    async with db.session() as conn:
        cursor = await conn.execute("SELECT city FROM users WHERE telegram_id = ?", (user_id,))
        row = await cursor.fetchone()
        if not row or not row[0]:
            await message.answer("Ваш город не определён.")
            return
        city = row[0]
        station_repo = StationRepository(conn)
        stations = await station_repo.get_by_city(city)
        if not stations:
            await message.answer("В вашем городе нет СТО.")
            return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=st.name, callback_data=f"reg_price_station_{st.id}")] for st in stations
    ])
    await state.set_state(RegionalAdminStates.choosing_station_for_price)
    await message.answer("Выберите СТО для загрузки прайса:", reply_markup=kb)


@router.callback_query(StateFilter(RegionalAdminStates.choosing_station_for_price), F.data.startswith("reg_price_station_"))
async def station_selected_for_price(callback: CallbackQuery, state: FSMContext):
    station_id = int(callback.data.split("_")[3])
    await state.update_data(station_id=station_id)
    await state.set_state(RegionalAdminStates.waiting_for_price_file_for_station)
    await callback.message.edit_text("📎 Отправьте Excel-файл с прайс-листом для этого СТО.")
    await callback.answer()


@router.message(StateFilter(RegionalAdminStates.waiting_for_price_file_for_station), F.document)
async def handle_price_file_for_station(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    station_id = data.get('station_id')
    if not station_id:
        await message.answer("Ошибка: не выбрано СТО.")
        await state.clear()
        return

    document = message.document
    if not document.file_name.endswith(('.xlsx', '.xls')):
        await message.answer("❌ Пожалуйста, отправьте файл в формате Excel (.xlsx или .xls)")
        return

    status_msg = await message.answer("⏳ Обрабатываем файл...")

    # FIX: безопасное создание временного файла
    temp_fd, file_path = tempfile.mkstemp(suffix=".xlsx", prefix="prices_station_")
    os.close(temp_fd)
    await bot.download_file(document.file_id, file_path)

    async with db.session() as conn:
        cursor = await conn.execute("SELECT city_id FROM stations WHERE id = ?", (station_id,))
        row = await cursor.fetchone()
        if not row:
            await message.answer("❌ СТО не найдено.")
            await state.clear()
            return
        city_id = row[0]
        cursor = await conn.execute("SELECT name FROM cities WHERE id = ?", (city_id,))
        city_row = await cursor.fetchone()
        city = city_row[0] if city_row else "Неизвестно"

    try:
        count = await parse_and_insert_prices(file_path, station_id, city, message.from_user.id)
        await status_msg.edit_text(f"✅ Успешно загружено {count} услуг для СТО.")
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка при обработке файла: {e}")
        logger.error(f"Ошибка импорта прайса для СТО {station_id}: {e}")
    finally:
        os.remove(file_path)
        await state.clear()


# ---------- Управление приоритетами СТО (заглушка) ----------
@router.message(F.text == "📋 Управление приоритетами СТО")
async def manage_priorities(message: Message, state: FSMContext):
    if not await is_regional_admin(message.from_user.id):
        return
    await message.answer("Функция в разработке. Скоро будет доступна.")


# ---------- Возврат в главное меню ----------
@router.message(F.text == "⬅ Главное меню")
async def back_to_main(message: Message, state: FSMContext):
    await state.clear()
    role = 'regional_admin'
    await message.answer("Главное меню:", reply_markup=main_menu_kb(role))