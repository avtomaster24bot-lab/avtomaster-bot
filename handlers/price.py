# handlers/price.py
import re
import logging
from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from repositories.user_repo import UserRepository  # <-- добавлен импорт
from states.client_states import ClientStates
from keyboards.reply import back_kb, main_menu_kb
from utils.helpers import get_user_role, stars_from_rating
from thefuzz import fuzz
from transliterate import translit

logger = logging.getLogger(__name__)
router = Router()

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.strip().lower()
    if re.search('[а-я]', text):
        try:
            text = translit(text, 'ru', reversed=True)
        except Exception:
            pass
    return text

@router.message(StateFilter(
    ClientStates.entering_price_brand,
    ClientStates.entering_price_model,
    ClientStates.entering_price_service
), F.text == "⬅ Назад")
async def back_from_price(message: Message, state: FSMContext):
    await state.clear()
    role = await get_user_role(message.from_user.id)
    await message.answer("Главное меню:", reply_markup=main_menu_kb(role))

@router.message(F.text == "💰 Узнать цену")
async def price_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    async with db.session() as conn:
        user_repo = UserRepository(conn)
        user = await user_repo.get_by_telegram_id(user_id)
        if not user or not user.city:
            await message.answer("Сначала выберите город в /start")
            return
        city = user.city
    await state.update_data(city=city)
    await state.set_state(ClientStates.entering_price_brand)
    await message.answer("Введите марку авто (например, Toyota):", reply_markup=back_kb())

@router.message(StateFilter(ClientStates.entering_price_brand))
async def price_brand_entered(message: Message, state: FSMContext):
    brand = message.text.strip()
    await state.update_data(brand=brand)
    await state.set_state(ClientStates.entering_price_model)
    await message.answer("Введите модель авто (например, Camry):", reply_markup=back_kb())

@router.message(StateFilter(ClientStates.entering_price_model))
async def price_model_entered(message: Message, state: FSMContext):
    model = message.text.strip()
    await state.update_data(model=model)
    await state.set_state(ClientStates.entering_price_service)
    await message.answer("Введите название услуги (например, замена масла):", reply_markup=back_kb())

@router.message(StateFilter(ClientStates.entering_price_service))
async def price_service_entered(message: Message, state: FSMContext):
    user_service = message.text.strip().lower()
    data = await state.get_data()
    city = data['city']
    user_brand = data['brand']
    user_model = data['model']

    norm_brand = normalize_text(user_brand)
    norm_model = normalize_text(user_model)
    norm_service = normalize_text(user_service)

    async with db.session() as conn:
        cursor = await conn.execute(
            "SELECT ss.id, ss.station_id, s.name, s.rating, ss.price, ss.service_name, ss.brand, ss.model "
            "FROM station_services ss JOIN stations s ON ss.station_id = s.id "
            "WHERE LOWER(ss.city) = LOWER(?)",
            (city,)
        )
        all_services = await cursor.fetchall()

    if not all_services:
        await message.answer(f"😕 В городе {city} пока нет загруженных услуг.")
        await state.clear()
        await message.answer("Главное меню:", reply_markup=main_menu_kb('client'))
        return

    matched = []
    for rec in all_services:
        service_id, station_id, station_name, rating, price, service_name, db_brand, db_model = rec
        db_brand_norm = normalize_text(db_brand)
        db_model_norm = normalize_text(db_model)
        db_service_norm = normalize_text(service_name)

        brand_score = fuzz.token_sort_ratio(norm_brand, db_brand_norm)
        model_score = fuzz.token_sort_ratio(norm_model, db_model_norm)
        service_score = fuzz.token_set_ratio(norm_service, db_service_norm)

        total_score = brand_score * 0.1 + model_score * 0.1 + service_score * 0.8
        if total_score >= 70:
            matched.append((total_score, service_id, station_id, station_name, rating, price, service_name, db_brand, db_model))

    matched.sort(key=lambda x: x[0], reverse=True)

    if not matched:
        await message.answer(f"😕 Не найдено предложений для {user_brand} {user_model} по услуге «{user_service}».")
        await state.clear()
        await message.answer("Главное меню:", reply_markup=main_menu_kb('client'))
        return

    await message.answer(f"🔍 Найдено предложений: {len(matched)}")
    for i, rec in enumerate(matched[:10]):
        score, service_id, station_id, name, rating, price, service_name, db_brand, db_model = rec
        stars = stars_from_rating(rating or 0)
        text = (
            f"🏢 *{name}*\n"
            f"⭐ {stars} ({rating or 0:.1f})\n"
            f"💰 *{price} KZT*\n"
            f"🚗 Марка/модель: {db_brand} {db_model}\n"
            f"🔧 Услуга: {service_name}\n"
            f"_{i+1}. Совпадение: {score:.0f}%_"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Записаться", callback_data=f"price_book_{service_id}")]
        ])
        await message.answer(text, parse_mode='Markdown', reply_markup=kb)

    await message.answer("Главное меню:", reply_markup=main_menu_kb('client'))
    await state.clear()