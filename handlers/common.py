from aiogram import Router, types, F
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton

from database import db
from repositories.user_repo import UserRepository
from services.user_service import UserService
from keyboards.reply import main_menu_kb
from keyboards.inline import inline_city_choice
from states.client_states import ClientStates
from utils.logger import logger

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    await state.clear()

    # Разбираем параметр ref_sto_<id>
    args = message.text.split()
    ref_station_id = None
    if len(args) > 1:
        param = args[1]
        if param.startswith("ref_sto_"):
            try:
                ref_station_id = int(param.split("_")[2])
                await state.update_data(ref_station_id=ref_station_id)
            except (IndexError, ValueError):
                pass

    async with db.session() as conn:
        user_repo = UserRepository(conn)
        user = await user_repo.get_by_telegram_id(user_id)

        if not user:
            full_name = message.from_user.full_name
            user_service = UserService(conn)
            await user_service.register_user(user_id, full_name)
            await message.answer(
                "👋 Добро пожаловать в AvtoMaster24!\nВыберите ваш город:",
                reply_markup=await inline_city_choice()
            )
            await state.set_state(ClientStates.choosing_city)
            return

        if user.role == 'global_admin':
            await message.answer("С возвращением, Глобальный администратор!", reply_markup=main_menu_kb(user.role))
            return

        if user.role == 'regional_admin':
            if not user.city:
                await message.answer("Выберите город:", reply_markup=await inline_city_choice())
                await state.set_state(ClientStates.choosing_city)
                return
            await message.answer(f"С возвращением, региональный администратор!\nВаш город: {user.city}", reply_markup=main_menu_kb(user.role))
            return

        if not user.city:
            await message.answer("Выберите ваш город:", reply_markup=await inline_city_choice())
            await state.set_state(ClientStates.choosing_city)
            return

        if not user.phone:
            await state.set_state(ClientStates.waiting_for_phone_start)
            kb = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)]],
                resize_keyboard=True, one_time_keyboard=True
            )
            await message.answer("📱 Для работы бота нужен номер телефона. Поделитесь, нажав кнопку.", reply_markup=kb)
            return

        # Если пользователь уже зарегистрирован и есть ref_station_id – показываем карточку
        data = await state.get_data()
        if data.get("ref_station_id"):
            from handlers.client import show_station_card_by_id
            await show_station_card_by_id(message, data["ref_station_id"], state, edit=False)
            await state.update_data(ref_station_id=None)
            return

        await message.answer(f"С возвращением! Ваш город: {user.city}\nГлавное меню:", reply_markup=main_menu_kb(user.role))

@router.callback_query(F.data.startswith("city_"))
async def city_chosen(callback: CallbackQuery, state: FSMContext):
    city_id = int(callback.data.split("_")[1])
    async with db.session() as conn:
        cursor = await conn.execute("SELECT name FROM cities WHERE id = ?", (city_id,))
        row = await cursor.fetchone()
        if not row:
            await callback.answer("Город не найден")
            return
        city_name = row[0]
        await conn.execute("UPDATE users SET city = ? WHERE telegram_id = ?", (city_name, callback.from_user.id))
        await conn.commit()

        # Проверяем наличие реферальной ссылки
        data = await state.get_data()
        if data.get("ref_station_id"):
            from handlers.client import show_station_card_by_id
            await show_station_card_by_id(callback.message, data["ref_station_id"], state, edit=False)
            await state.update_data(ref_station_id=None)
            await callback.answer()
            return

        user_repo = UserRepository(conn)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        if not user.phone:
            await state.set_state(ClientStates.waiting_for_phone_start)
            kb = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)]],
                resize_keyboard=True, one_time_keyboard=True
            )
            await callback.message.answer("📱 Поделитесь номером телефона.", reply_markup=kb)
        else:
            await callback.message.answer("Главное меню:", reply_markup=main_menu_kb(user.role))
    await callback.answer()

@router.message(StateFilter(ClientStates.waiting_for_phone_start), F.contact)
async def phone_received_start(message: Message, state: FSMContext):
    contact = message.contact
    if contact.user_id != message.from_user.id:
        await message.answer("❌ Отправьте свой номер.")
        return
    phone = contact.phone_number
    full_name = message.from_user.full_name
    async with db.session() as conn:
        await conn.execute("UPDATE users SET phone = ?, full_name = ? WHERE telegram_id = ?", (phone, full_name, message.from_user.id))
        await conn.commit()
        user_repo = UserRepository(conn)
        user = await user_repo.get_by_telegram_id(message.from_user.id)

    # Проверяем реферальную ссылку
    data = await state.get_data()
    if data.get("ref_station_id"):
        from handlers.client import show_station_card_by_id
        await show_station_card_by_id(message, data["ref_station_id"], state, edit=False)
        await state.update_data(ref_station_id=None)
        await state.clear()
        return

    await message.answer("✅ Спасибо! Номер сохранён.")
    await state.clear()
    await message.answer("Главное меню:", reply_markup=main_menu_kb(user.role))

@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer("Это бот-помощник для автовладельцев. Вы можете:\n🚗 Найти автосервис\n🚿 Записаться на мойку\n🚨 Вызвать эвакуатор\n🛒 Купить запчасти\n💬 Спросить совет у ИИ\nИ многое другое.")

@router.message(F.text == "⬅ Главное меню")
async def back_to_main(message: Message, state: FSMContext):
    await state.clear()
    async with db.session() as conn:
        user_repo = UserRepository(conn)
        user = await user_repo.get_by_telegram_id(message.from_user.id)
        role = user.role if user else 'client'
    await message.answer("Главное меню:", reply_markup=main_menu_kb(role))