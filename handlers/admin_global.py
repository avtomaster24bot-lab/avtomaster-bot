# handlers/admin_global.py
import logging
from aiogram import Router, F, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from database import db
from repositories.user_repo import UserRepository
from states.admin_states import GlobalAdminStates
from keyboards.reply import main_menu_kb
from keyboards.inline import inline_city_choice
from utils.helpers import get_city_id

logger = logging.getLogger(__name__)
router = Router()


async def is_global_admin(user_id: int) -> bool:
    async with db.session() as conn:
        cursor = await conn.execute("SELECT role FROM users WHERE telegram_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row and row[0] == 'global_admin'


# ---------- Панель главного админа ----------
@router.message(F.text == "🌍 Панель главного админа")
async def global_panel(message: Message, state: FSMContext):
    if not await is_global_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    kb = types.ReplyKeyboardMarkup(keyboard=[
        [types.KeyboardButton(text="➕ Добавить город")],
        [types.KeyboardButton(text="➕ Назначить регионального админа")],
        [types.KeyboardButton(text="📊 Глобальная статистика")],
        [types.KeyboardButton(text="🏙 Список городов")],
        [types.KeyboardButton(text="⬅ Главное меню")]
    ], resize_keyboard=True)
    await message.answer("Панель главного администратора", reply_markup=kb)


# ---------- Добавление города ----------
@router.message(F.text == "➕ Добавить город")
async def add_city_start(message: Message, state: FSMContext):
    if not await is_global_admin(message.from_user.id):
        return
    await state.set_state(GlobalAdminStates.adding_city)
    await message.answer("Введите название нового города:")


@router.message(StateFilter(GlobalAdminStates.adding_city))
async def add_city(message: Message, state: FSMContext):
    city = message.text.strip()
    if not city:
        await message.answer("Название города не может быть пустым.")
        return
    async with db.session() as conn:
        try:
            await conn.execute("INSERT INTO cities (name) VALUES (?)", (city,))
            await conn.commit()
            await message.answer(f"✅ Город «{city}» добавлен.")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}")
    await state.clear()


# ---------- Назначение регионального админа ----------
@router.message(F.text == "➕ Назначить регионального админа")
async def assign_regional_start(message: Message, state: FSMContext):
    if not await is_global_admin(message.from_user.id):
        return
    await state.set_state(GlobalAdminStates.entering_regional_id)
    await message.answer("Введите Telegram ID пользователя, которого хотите сделать региональным админом:")


@router.message(StateFilter(GlobalAdminStates.entering_regional_id))
async def assign_regional_id(message: Message, state: FSMContext):
    try:
        target_id = int(message.text)
    except ValueError:
        await message.answer("❌ Введите корректный числовой ID.")
        return
    # Проверим, не является ли этот пользователь уже глобальным админом
    async with db.session() as conn:
        cursor = await conn.execute("SELECT role FROM users WHERE telegram_id = ?", (target_id,))
        row = await cursor.fetchone()
        if row and row[0] == 'global_admin':
            await message.answer("❌ Нельзя назначить глобального администратора региональным.")
            await state.clear()
            return
    await state.update_data(target_id=target_id)
    await message.answer(
        "Выберите город, за который он будет отвечать:",
        reply_markup=await inline_city_choice()
    )
    await state.set_state(GlobalAdminStates.entering_regional_city)


@router.callback_query(StateFilter(GlobalAdminStates.entering_regional_city), F.data.startswith("city_"))
async def assign_regional_city_chosen(callback: CallbackQuery, state: FSMContext):
    city_id = int(callback.data.split("_")[1])
    data = await state.get_data()
    target_id = data['target_id']

    async with db.session() as conn:
        cursor = await conn.execute("SELECT name FROM cities WHERE id = ?", (city_id,))
        city_row = await cursor.fetchone()
        if not city_row:
            await callback.answer("Город не найден.")
            return
        city = city_row[0]

        # Проверяем, существует ли пользователь
        user_repo = UserRepository(conn)
        user = await user_repo.get_by_telegram_id(target_id)
        if user:
            await conn.execute(
                "UPDATE users SET role = 'regional_admin', city = ? WHERE telegram_id = ?",
                (city, target_id)
            )
        else:
            await conn.execute(
                "INSERT INTO users (telegram_id, role, city) VALUES (?, ?, ?)",
                (target_id, 'regional_admin', city)
            )
        await conn.commit()

    await callback.message.edit_text(
        f"✅ Пользователь {target_id} назначен региональным админом города «{city}».\n"
        f"Теперь он может зайти в бота и нажать /start."
    )
    await state.clear()
    await callback.answer()


# ---------- Глобальная статистика ----------
@router.message(F.text == "📊 Глобальная статистика")
async def global_stats(message: Message):
    if not await is_global_admin(message.from_user.id):
        return
    async with db.session() as conn:
        users = await (await conn.execute("SELECT COUNT(*) FROM users")).fetchone()
        requests = await (await conn.execute("SELECT COUNT(*) FROM requests")).fetchone()
        stations = await (await conn.execute("SELECT COUNT(*) FROM stations")).fetchone()
        washes = await (await conn.execute("SELECT COUNT(*) FROM car_washes")).fetchone()
        tows = await (await conn.execute("SELECT COUNT(*) FROM tow_trucks")).fetchone()
        suppliers = await (await conn.execute("SELECT COUNT(*) FROM suppliers")).fetchone()
        providers = await (await conn.execute("SELECT COUNT(*) FROM service_providers")).fetchone()
    text = (
        f"📊 Глобальная статистика:\n"
        f"Пользователей: {users[0]}\n"
        f"Заявок: {requests[0]}\n"
        f"СТО: {stations[0]}\n"
        f"Моек: {washes[0]}\n"
        f"Эвакуаторов: {tows[0]}\n"
        f"Поставщиков: {suppliers[0]}\n"
        f"Специалистов срочных услуг: {providers[0]}"
    )
    await message.answer(text)


# ---------- Список городов ----------
@router.message(F.text == "🏙 Список городов")
async def list_cities(message: Message):
    if not await is_global_admin(message.from_user.id):
        return
    async with db.session() as conn:
        cursor = await conn.execute("SELECT id, name FROM cities ORDER BY name")
        cities = await cursor.fetchall()
    if not cities:
        await message.answer("Городов пока нет.")
        return
    text = "🏙 Список городов:\n"
    for city_id, name in cities:
        text += f"• {name} (ID: {city_id})\n"
    await message.answer(text)


# ---------- Возврат в главное меню ----------
@router.message(F.text == "⬅ Главное меню")
async def back_to_main(message: Message, state: FSMContext):
    await state.clear()
    role = 'global_admin'
    await message.answer("Главное меню:", reply_markup=main_menu_kb(role))