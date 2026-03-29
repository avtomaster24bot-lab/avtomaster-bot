# handlers/service_book.py
import json
from aiogram import Router, F, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from database import db
import aiosqlite
from datetime import datetime
from keyboards.reply import main_menu_kb, back_kb
from states.client_states import ClientStates
from keyboards.inline import cars_list_kb

router = Router()

# Удалён блок @router.message(F.text == "📊 История заявок") – дубликат.

@router.message(F.text == "⭐ Мои отзывы")
async def show_my_reviews(message: Message):
    user_id = message.from_user.id
    async with db.session() as conn:
        cursor = await conn.execute('''
            SELECT id, entity_type, rating, comment, created_at
            FROM reviews
            WHERE user_id = ?
            ORDER BY created_at DESC
        ''', (user_id,))
        reviews = await cursor.fetchall()
    if not reviews:
        await message.answer("Вы ещё не оставляли отзывов.")
        return
    text = "⭐ Ваши отзывы:\n\n"
    for rev in reviews:
        rev_id, etype, rating, comment, created_at = rev
        date_str = datetime.fromisoformat(created_at).strftime("%d.%m.%Y")
        stars = "⭐" * rating
        comment_display = comment if comment else "(нет комментария)"
        text += f"{stars} ({rating}/5) на {etype} от {date_str}\n"
        text += f"   «{comment_display}»\n\n"
    await message.answer(text)


@router.message(F.text == "📒 Сервисная книжка")
async def service_book_menu(message: Message, state: FSMContext):
    user_id = message.from_user.id
    async with db.session() as conn:
        cursor = await conn.execute("SELECT id, brand, model, year, license_plate FROM user_cars WHERE user_id = ?", (user_id,))
        cars = await cursor.fetchall()
    if not cars:
        await message.answer(
            "У вас пока нет добавленных автомобилей. Хотите добавить?",
            reply_markup=types.ReplyKeyboardMarkup(keyboard=[
                [types.KeyboardButton(text="➕ Добавить авто")],
                [types.KeyboardButton(text="⬅ Главное меню")]
            ], resize_keyboard=True)
        )
        await state.set_state(ClientStates.adding_car_brand)
    else:
        await message.answer("Выберите автомобиль:", reply_markup=cars_list_kb(cars))
        await state.set_state(ClientStates.choosing_car)


@router.callback_query(StateFilter(ClientStates.choosing_car), F.data.startswith("car_"))
async def show_car_history(callback: CallbackQuery, state: FSMContext):
    car_id = int(callback.data.split("_")[1])
    async with db.session() as conn:
        cursor = await conn.execute('''
            SELECT brand, model, year, license_plate FROM user_cars WHERE id = ?
        ''', (car_id,))
        car = await cursor.fetchone()
        if not car:
            await callback.answer("Автомобиль не найден")
            return
        brand, model, year, plate = car
        cursor = await conn.execute('''
            SELECT date, mileage, description, service_type, cost
            FROM service_records
            WHERE car_id = ?
            ORDER BY date DESC
        ''', (car_id,))
        records = await cursor.fetchall()
    text = f"📒 {brand} {model} {year}\n"
    if plate:
        text += f"Госномер: {plate}\n"
    text += "\nИстория обслуживания:\n"
    if not records:
        text += "Пока нет записей.\n"
    else:
        for rec in records:
            date, mileage, desc, stype, cost = rec
            text += f"📅 {date} | пробег {mileage} км | {stype}\n   {desc}\n   💰 {cost} KZT\n"
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="➕ Добавить запись", callback_data=f"add_record_{car_id}")],
        [types.InlineKeyboardButton(text="⬅ К списку авто", callback_data="back_to_cars")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await state.update_data(car_id=car_id)
    await state.set_state(ClientStates.viewing_car)
    await callback.answer()


@router.callback_query(StateFilter(ClientStates.viewing_car), F.data.startswith("add_record_"))
async def add_record_start(callback: CallbackQuery, state: FSMContext):
    car_id = int(callback.data.split("_")[2])
    await state.update_data(car_id=car_id)
    await state.set_state(ClientStates.adding_record_date)
    await callback.message.answer("Введите дату (ГГГГ-ММ-ДД) или нажмите /today для сегодняшней:", reply_markup=back_kb())
    await callback.answer()


@router.message(StateFilter(ClientStates.adding_record_date))
async def add_record_date(message: Message, state: FSMContext):
    date_text = message.text
    if date_text == "/today":
        date = datetime.now().strftime("%Y-%m-%d")
    else:
        date = date_text
    await state.update_data(record_date=date)
    await state.set_state(ClientStates.adding_record_mileage)
    await message.answer("Введите пробег (км):")


@router.message(StateFilter(ClientStates.adding_record_mileage))
async def add_record_mileage(message: Message, state: FSMContext):
    mileage = message.text
    if not mileage.isdigit():
        await message.answer("Пожалуйста, введите число.")
        return
    await state.update_data(mileage=int(mileage))
    await state.set_state(ClientStates.adding_record_desc)
    await message.answer("Краткое описание работ (например, 'замена масла'):")


@router.message(StateFilter(ClientStates.adding_record_desc))
async def add_record_desc(message: Message, state: FSMContext):
    desc = message.text
    await state.update_data(desc=desc)
    await state.set_state(ClientStates.adding_record_cost)
    await message.answer("Стоимость работ (KZT):")


@router.message(StateFilter(ClientStates.adding_record_cost))
async def add_record_cost(message: Message, state: FSMContext):
    cost = message.text
    if not cost.isdigit():
        await message.answer("Введите число.")
        return
    data = await state.get_data()
    user_id = message.from_user.id
    car_id = data['car_id']
    date = data['record_date']
    mileage = data['mileage']
    desc = data['desc']
    cost_int = int(cost)
    async with db.session() as conn:
        await conn.execute('''
            INSERT INTO service_records (user_id, car_id, date, mileage, description, service_type, cost)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, car_id, date, mileage, desc, 'manual', cost_int))
        await conn.commit()
    await message.answer("✅ Запись добавлена в сервисную книжку.")
    await state.clear()
    await service_book_menu(message, state)


@router.callback_query(F.data == "back_to_cars")
async def back_to_cars(callback: CallbackQuery, state: FSMContext):
    await service_book_menu(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "add_car")
async def add_car_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ClientStates.adding_car_brand)
    await callback.message.answer("Введите марку автомобиля (например, Toyota):", reply_markup=back_kb())
    await callback.answer()


@router.message(StateFilter(ClientStates.adding_car_brand))
async def add_car_brand(message: Message, state: FSMContext):
    brand = message.text
    await state.update_data(brand=brand)
    await state.set_state(ClientStates.adding_car_model)
    await message.answer("Введите модель:")


@router.message(StateFilter(ClientStates.adding_car_model))
async def add_car_model(message: Message, state: FSMContext):
    model = message.text
    await state.update_data(model=model)
    await state.set_state(ClientStates.adding_car_year)
    await message.answer("Введите год выпуска (например, 2015):")


@router.message(StateFilter(ClientStates.adding_car_year))
async def add_car_year(message: Message, state: FSMContext):
    year = message.text
    if not year.isdigit() or len(year) != 4:
        await message.answer("Пожалуйста, введите корректный год (4 цифры).")
        return
    await state.update_data(year=int(year))
    await state.set_state(ClientStates.adding_car_plate)
    await message.answer("Введите госномер (необязательно, можно пропустить /skip):")


@router.message(StateFilter(ClientStates.adding_car_plate))
async def add_car_plate(message: Message, state: FSMContext):
    plate = message.text
    if plate == "/skip":
        plate = None
    data = await state.get_data()
    user_id = message.from_user.id
    async with db.session() as conn:
        await conn.execute('''
            INSERT INTO user_cars (user_id, brand, model, year, license_plate)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, data['brand'], data['model'], data['year'], plate))
        await conn.commit()
    await message.answer("✅ Автомобиль добавлен в сервисную книжку.")
    await state.clear()
    await service_book_menu(message, state)