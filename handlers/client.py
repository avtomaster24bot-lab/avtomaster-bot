# handlers/client.py
import json
import asyncio
from datetime import datetime, timedelta
from collections import Counter
import logging

from aiogram import Router, F, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from repositories.user_repo import UserRepository
from repositories.category_repo import CategoryRepository
from repositories.subcategory_repo import SubcategoryRepository
from repositories.station_repo import StationRepository
from repositories.car_wash_repo import CarWashRepository
from repositories.tow_truck_repo import TowTruckRepository
from repositories.supplier_repo import SupplierRepository
from repositories.service_provider_repo import ServiceProviderRepository
from repositories.request_repo import RequestRepository
from services.request_service import RequestService
from keyboards.reply import main_menu_kb, back_kb
from keyboards.inline import (
    category_choice_kb, subcategory_choice_with_checkbox_kb,
    wash_list_kb, cars_list_kb, roadside_services_kb,
    cancel_part_request_kb
)
from states.client_states import ClientStates
from utils.helpers import (
    stars_from_rating, get_user_city, update_offers_message,
    notify_regional_admin, get_user_role,
    notify_regional_admin_about_review
)
from utils.geo import haversine

logger = logging.getLogger(__name__)
router = Router()

# ========== ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ БЕЗОПАСНОГО УДАЛЕНИЯ ==========
async def delete_message(obj: Message | CallbackQuery):
    try:
        if isinstance(obj, CallbackQuery):
            await obj.message.delete()
        else:
            await obj.delete()
    except Exception:
        pass

# ========== ОБРАБОТЧИК ГЛАВНОГО МЕНЮ ==========
@router.callback_query(F.data == "back_to_main")
async def back_to_main_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    role = await get_user_role(callback.from_user.id)
    await delete_message(callback)
    await callback.message.answer("Главное меню:", reply_markup=main_menu_kb(role))
    await callback.answer()

# ========== СТО ==========
@router.message(F.text == "🚗 Найти автосервис")
async def find_sto(message: Message, state: FSMContext):
    user_id = message.from_user.id
    async with db.session() as conn:
        user_repo = UserRepository(conn)
        user = await user_repo.get_by_telegram_id(user_id)
        if not user or not user.city:
            await message.answer("Сначала выберите город в /start")
            return
        city = user.city
        category_repo = CategoryRepository(conn)
        categories = await category_repo.get_by_city(city)
        if not categories:
            await message.answer("В вашем городе пока нет доступных категорий.")
            return
        await state.update_data(city=city)
        await state.set_state(ClientStates.choosing_sto_category)
        await message.answer("Выберите категорию услуги:", reply_markup=category_choice_kb(categories))

@router.callback_query(StateFilter(ClientStates.choosing_sto_category), F.data.startswith("cat_"))
async def sto_category_chosen(callback: CallbackQuery, state: FSMContext):
    category_id = int(callback.data.split("_")[1])
    logger.info(f"Выбрана категория ID={category_id}")
    async with db.session() as conn:
        sub_repo = SubcategoryRepository(conn)
        subcategories = await sub_repo.get_by_category_id(category_id)
        logger.info(f"Найдено подкатегорий: {len(subcategories)}")
        category_repo = CategoryRepository(conn)
        category = await category_repo.get_by_id(category_id)
        if category:
            await state.update_data(category_name=category.name)
        await state.update_data(category_id=category_id)
        await state.set_state(ClientStates.choosing_sto_subcategories)
        await callback.message.edit_text(
            "Выберите подуслуги:",
            reply_markup=subcategory_choice_with_checkbox_kb(subcategories, [])
        )
    await callback.answer()

@router.callback_query(StateFilter(ClientStates.choosing_sto_subcategories), F.data.startswith("sub_toggle_"))
async def sto_subcategory_toggle(callback: CallbackQuery, state: FSMContext):
    sub_id = int(callback.data.split("_")[2])
    data = await state.get_data()
    selected = data.get('selected_subs', [])
    if sub_id in selected:
        selected.remove(sub_id)
    else:
        selected.append(sub_id)
    await state.update_data(selected_subs=selected)
    async with db.session() as conn:
        sub_repo = SubcategoryRepository(conn)
        subs = await sub_repo.get_by_category_id(data['category_id'])
        await callback.message.edit_reply_markup(
            reply_markup=subcategory_choice_with_checkbox_kb(subs, selected)
        )
    await callback.answer()

@router.callback_query(StateFilter(ClientStates.choosing_sto_subcategories), F.data == "sub_done")
async def sto_subcategories_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_ids = data.get('selected_subs', [])
    if selected_ids:
        async with db.session() as conn:
            sub_repo = SubcategoryRepository(conn)
            subs = await sub_repo.get_by_ids(selected_ids)
            sub_names = [s.name for s in subs]
            await state.update_data(sub_names=sub_names)
    await state.set_state(ClientStates.entering_sto_description)
    await delete_message(callback)
    await callback.message.answer("Опишите проблему подробнее:", reply_markup=back_kb())
    await callback.answer()

# ---------- Кнопка "Назад" в выборе подуслуг ----------
@router.callback_query(StateFilter(ClientStates.choosing_sto_subcategories), F.data == "sub_back")
async def back_to_sto_category(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    city = await get_user_city(user_id)
    if not city:
        await callback.message.edit_text("Ошибка: город не найден.")
        await state.clear()
        return
    async with db.session() as conn:
        category_repo = CategoryRepository(conn)
        categories = await category_repo.get_by_city(city)
    await state.set_state(ClientStates.choosing_sto_category)
    await callback.message.edit_text(
        "Выберите категорию услуги:",
        reply_markup=category_choice_kb(categories)
    )
    await callback.answer()

@router.message(StateFilter(ClientStates.entering_sto_description), F.text == "⬅ Назад")
async def back_to_sto_subcategories(message: Message, state: FSMContext):
    data = await state.get_data()
    category_id = data.get('category_id')
    if not category_id:
        await state.set_state(ClientStates.choosing_sto_category)
        await message.answer("Начните заново.", reply_markup=main_menu_kb('client'))
        return
    async with db.session() as conn:
        sub_repo = SubcategoryRepository(conn)
        subs = await sub_repo.get_by_category_id(category_id)
        selected_ids = data.get('selected_subs', [])
        await state.set_state(ClientStates.choosing_sto_subcategories)
        await delete_message(message)
        await message.answer(
            "Выберите подуслуги:",
            reply_markup=subcategory_choice_with_checkbox_kb(subs, selected_ids)
        )

@router.message(StateFilter(ClientStates.entering_sto_description))
async def sto_description_entered(message: Message, state: FSMContext):
    desc = message.text
    await state.update_data(description=desc)

    data = await state.get_data()
    # Если есть target_station_id (из реферальной ссылки) – сразу создаём заявку для этого СТО
    target_station_id = data.get("target_station_id")
    if target_station_id:
        user_id = message.from_user.id
        async with db.session() as conn:
            request_service = RequestService(conn)
            request_id = await request_service.create_request(
                user_id=user_id,
                req_type='sto',
                city=data['city'],
                description=desc,
                category_id=data['category_id'],
                subcategories=data.get('selected_subs', []),
                accepted_by=target_station_id
            )
            # Уведомляем выбранное СТО
            station_repo = StationRepository(conn)
            station = await station_repo.get_by_id(target_station_id)
            if station and station.admin_id:
                await message.bot.send_message(station.admin_id, f"Новая заявка #{request_id} назначена вам (по реферальной ссылке).")
        await delete_message(message)
        await message.answer(f"✅ Заявка #{request_id} отправлена выбранному СТО.", reply_markup=main_menu_kb('client'))
        await state.clear()
        return

    # Обычный путь – показываем выбор: всем или конкретному СТО
    await state.set_state(ClientStates.confirming_sto_request)
    cat_name = data.get('category_name', '')
    sub_names = data.get('sub_names', [])
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📢 Всем подходящим СТО")],
        [KeyboardButton(text="🎯 Выбрать конкретное СТО")],
        [KeyboardButton(text="❌ Отмена")]
    ], resize_keyboard=True)
    text = f"📝 Подтвердите заявку:\nКатегория: {cat_name}\n"
    if sub_names:
        text += f"Подуслуги: {', '.join(sub_names)}\n"
    text += f"Описание: {desc}\n\nВыберите, кому отправить заявку:"
    await delete_message(message)
    await message.answer(text, reply_markup=kb)

@router.message(StateFilter(ClientStates.confirming_sto_request), F.text == "📢 Всем подходящим СТО")
async def sto_request_to_all(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id
    async with db.session() as conn:
        request_service = RequestService(conn)
        request_id = await request_service.create_request(
            user_id=user_id,
            req_type='sto',
            city=data['city'],
            description=data['description'],
            category_id=data['category_id'],
            subcategories=data.get('selected_subs', [])
        )
        await request_service.notify_executors(request_id, 'sto', data['city'], message.bot)
    await delete_message(message)
    await message.answer(f"✅ Заявка #{request_id} отправлена всем подходящим СТО.", reply_markup=main_menu_kb('client'))
    await state.clear()

@router.message(StateFilter(ClientStates.confirming_sto_request), F.text == "🎯 Выбрать конкретное СТО")
async def sto_request_choose_station(message: Message, state: FSMContext):
    data = await state.get_data()
    city = data['city']
    category_id = data['category_id']
    async with db.session() as conn:
        station_repo = StationRepository(conn)
        stations = await station_repo.get_by_category_and_city(category_id, city)
        if not stations:
            await message.answer("Нет доступных СТО для выбранной категории.")
            return
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"{s.name} ⭐{s.rating:.1f}", callback_data=f"choose_sto_{s.id}")] for s in stations
        ])
        await state.set_state(ClientStates.choosing_specific_sto)
        await delete_message(message)
        await message.answer("Выберите СТО:", reply_markup=kb)

@router.callback_query(StateFilter(ClientStates.choosing_specific_sto), F.data.startswith("choose_sto_"))
async def show_station_card(callback: CallbackQuery, state: FSMContext):
    station_id = int(callback.data.split("_")[2])
    async with db.session() as conn:
        station_repo = StationRepository(conn)
        station = await station_repo.get_by_id(station_id)
        if not station:
            await callback.answer("СТО не найдено")
            return
        stars = stars_from_rating(station.rating or 0)
        text = (
            f"🏢 {station.name}\n"
            f"⭐ Рейтинг: {stars} ({station.rating:.1f} на основе {station.reviews_count} отзывов)\n"
            f"📍 Адрес: {station.address or 'не указан'}\n"
            f"📞 Телефон: {station.phone or 'не указан'}\n\n"
            "Выберите действие:"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Выбрать это СТО", callback_data=f"select_sto_{station_id}")],
            [InlineKeyboardButton(text="⭐ Посмотреть отзывы", callback_data=f"view_reviews_sto_{station_id}")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
        ])
        await callback.message.edit_text(text, reply_markup=kb)
        await state.update_data(station_id=station_id)
        await state.set_state(ClientStates.viewing_station)
    await callback.answer()

@router.callback_query(StateFilter(ClientStates.viewing_station), F.data.startswith("select_sto_"))
async def select_station(callback: CallbackQuery, state: FSMContext):
    station_id = int(callback.data.split("_")[2])
    data = await state.get_data()
    # Проверяем, есть ли данные для заявки
    if not data.get("city") or not data.get("description") or not data.get("category_id"):
        await callback.answer("Сначала создайте заявку через меню '🚗 Найти автосервис'", show_alert=True)
        return
    user_id = callback.from_user.id
    async with db.session() as conn:
        request_service = RequestService(conn)
        request_id = await request_service.create_request(
            user_id=user_id,
            req_type='sto',
            city=data['city'],
            description=data['description'],
            category_id=data['category_id'],
            subcategories=data.get('selected_subs', []),
            accepted_by=station_id
        )
        station_repo = StationRepository(conn)
        station = await station_repo.get_by_id(station_id)
        if station and station.admin_id:
            await callback.bot.send_message(station.admin_id, f"Новая заявка #{request_id} назначена вам.")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"✅ Заявка #{request_id} отправлена выбранному СТО.", reply_markup=main_menu_kb('client'))
    await state.clear()
    await callback.answer()

@router.message(StateFilter(ClientStates.confirming_sto_request), F.text == "❌ Отмена")
async def sto_request_cancel(message: Message, state: FSMContext):
    await delete_message(message)
    await message.answer("Заявка отменена.", reply_markup=main_menu_kb('client'))
    await state.clear()

# ... (остальные обработчики: мойка, эвакуатор, автопомощь, запчасти, история, сервисная книжка, отзывы, настройки и т.д.) ...
# Они остаются без изменений. Я не привожу их здесь для краткости, но в вашем полном файле они есть.

# ========== НОВЫЙ ОБРАБОТЧИК ДЛЯ СОЗДАНИЯ ЗАЯВКИ ПО РЕФЕРАЛЬНОЙ ССЫЛКЕ ==========
@router.callback_query(F.data.startswith("create_req_for_sto_"))
async def create_request_for_station(callback: CallbackQuery, state: FSMContext):
    station_id = int(callback.data.split("_")[4])
    await state.update_data(target_station_id=station_id)
    # Запускаем процесс создания заявки, начиная с выбора категории
    user_id = callback.from_user.id
    async with db.session() as conn:
        user_repo = UserRepository(conn)
        user = await user_repo.get_by_telegram_id(user_id)
        if not user or not user.city:
            await callback.message.answer("Сначала выберите город в /start")
            return
        city = user.city
        category_repo = CategoryRepository(conn)
        categories = await category_repo.get_by_city(city)
        if not categories:
            await callback.message.answer("В вашем городе пока нет доступных категорий.")
            return
        await state.update_data(city=city)
        await state.set_state(ClientStates.choosing_sto_category)
        await callback.message.answer("Выберите категорию услуги:", reply_markup=category_choice_kb(categories))
    await callback.answer()

# ========== МОДИФИЦИРОВАННАЯ ФУНКЦИЯ ПОКАЗА КАРТОЧКИ СТО (ДЛЯ РЕФЕРАЛЬНОЙ ССЫЛКИ) ==========
async def show_station_card_by_id(message: types.Message, station_id: int, state: FSMContext, edit: bool = False):
    async with db.session() as conn:
        station_repo = StationRepository(conn)
        station = await station_repo.get_by_id(station_id)
        if not station:
            if edit:
                await message.edit_text("СТО не найдено")
            else:
                await message.answer("СТО не найдено")
            return
        stars = stars_from_rating(station.rating or 0)
        text = (
            f"🏢 {station.name}\n"
            f"⭐ Рейтинг: {stars} ({station.rating:.1f} на основе {station.reviews_count} отзывов)\n"
            f"📍 Адрес: {station.address or 'не указан'}\n"
            f"📞 Телефон: {station.phone or 'не указан'}\n\n"
            "Выберите действие:"
        )
        # Заменяем кнопку "Выбрать это СТО" на "📝 Создать заявку"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Создать заявку", callback_data=f"create_req_for_sto_{station_id}")],
            [InlineKeyboardButton(text="⭐ Посмотреть отзывы", callback_data=f"view_reviews_sto_{station_id}")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
        ])
        if edit:
            await message.edit_text(text, reply_markup=kb)
        else:
            await message.answer(text, reply_markup=kb)
        await state.update_data(station_id=station_id)
        await state.set_state(ClientStates.viewing_station)

# ... (остальные обработчики: мойка, эвакуатор, автопомощь, запчасти, история, сервисная книжка, отзывы, настройки и т.д.) ...

# ========== АВТОМОЙКА ==========
@router.message(F.text == "🚿 Автомойка")
async def list_washes(message: Message, state: FSMContext):
    user_id = message.from_user.id
    city = await get_user_city(user_id)
    if not city:
        await message.answer("Сначала выберите город в /start")
        return
    async with db.session() as conn:
        wash_repo = CarWashRepository(conn)
        washes = await wash_repo.get_by_city(city)
        if not washes:
            await message.answer("В вашем городе пока нет автомоек.")
            return
        await state.set_state(ClientStates.choosing_wash)
        await state.update_data(city=city)
        wash_list = [(w.id, w.name, w.address, w.rating) for w in washes]
        await message.answer("Выберите мойку:", reply_markup=wash_list_kb(wash_list))

@router.callback_query(StateFilter(ClientStates.choosing_wash), F.data.startswith("wash_"))
async def show_wash_card(callback: CallbackQuery, state: FSMContext):
    wash_id = int(callback.data.split("_")[1])
    async with db.session() as conn:
        wash_repo = CarWashRepository(conn)
        wash = await wash_repo.get_by_id(wash_id)
        if not wash:
            await callback.answer("Мойка не найдена")
            return
        stars = stars_from_rating(wash.rating or 0)
        text = (
            f"🚿 {wash.name}\n"
            f"⭐ Рейтинг: {stars} ({wash.rating:.1f} на основе {wash.reviews_count} отзывов)\n"
            f"📍 Адрес: {wash.address or 'не указан'}\n"
            f"📞 Телефон: {wash.phone or 'не указан'}\n"
            f"🚗 Количество боксов: {wash.boxes}\n"
            f"⏱ Длительность услуги: {wash.slot_duration} мин\n\n"
            "Выберите действие:"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Записаться", callback_data=f"book_wash_{wash_id}")],
            [InlineKeyboardButton(text="⭐ Посмотреть отзывы", callback_data=f"view_reviews_car_wash_{wash_id}")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
        ])
        await callback.message.edit_text(text, reply_markup=kb)
        await state.update_data(wash_id=wash_id)
        await state.set_state(ClientStates.viewing_wash)
    await callback.answer()

@router.callback_query(StateFilter(ClientStates.viewing_wash), F.data.startswith("book_wash_"))
async def book_wash(callback: CallbackQuery, state: FSMContext):
    wash_id = int(callback.data.split("_")[2])
    await state.update_data(wash_id=wash_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for i in range(7):
        date = (datetime.now() + timedelta(days=i)).strftime("%Y-%m-%d")
        kb.inline_keyboard.append([InlineKeyboardButton(text=date, callback_data=f"wdate_{date}")])
    await state.set_state(ClientStates.choosing_wash_date)
    await callback.message.edit_text("Выберите дату:", reply_markup=kb)
    await callback.answer()

@router.callback_query(StateFilter(ClientStates.choosing_wash_date), F.data.startswith("wdate_"))
async def wash_date_chosen(callback: CallbackQuery, state: FSMContext):
    date = callback.data.split("_")[1]
    await state.update_data(wash_date=date)
    data = await state.get_data()
    wash_id = data['wash_id']
    now = datetime.now()
    async with db.session() as conn:
        cursor = await conn.execute(
            "SELECT datetime FROM wash_slots WHERE wash_id = ? AND date(datetime) = ? AND status = 'free' ORDER BY datetime",
            (wash_id, date)
        )
        rows = await cursor.fetchall()
        slots = []
        for (dt_str,) in rows:
            dt = datetime.fromisoformat(dt_str.replace(' ', 'T'))
            if dt.date() == now.date() and dt <= now:
                continue
            slots.append(dt_str)
        if not slots:
            await callback.message.edit_text("На эту дату нет свободных слотов. Выберите другую дату.")
            return
        time_list = [s.split(' ')[1][:5] for s in slots]
        time_counts = Counter(time_list)
        buttons = []
        for time_str in sorted(time_counts.keys()):
            count = time_counts[time_str]
            text = f"🟢 {time_str} ({count} мест)"
            buttons.append([InlineKeyboardButton(text=text, callback_data=f"wslot_time_{time_str}")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.edit_text("Выберите время:", reply_markup=kb)
        await state.set_state(ClientStates.choosing_wash_time)
    await callback.answer()

@router.callback_query(StateFilter(ClientStates.choosing_wash_time), F.data.startswith("wslot_time_"))
async def wash_slot_chosen(callback: CallbackQuery, state: FSMContext):
    time_str = callback.data.split("_")[2]
    data = await state.get_data()
    wash_id = data.get('wash_id')
    wash_date = data.get('wash_date')
    user_id = callback.from_user.id
    city = data.get('city')
    if not wash_date or not wash_id:
        await callback.answer("Ошибка: данные не найдены. Начните заново.", show_alert=True)
        await state.clear()
        return

    async with db.session() as conn:
        # Проверка, не записан ли уже клиент на это время
        cursor = await conn.execute(
            "SELECT id FROM wash_slots WHERE wash_id = ? AND date(datetime) = ? AND strftime('%H:%M', datetime) = ? AND user_id = ? AND status = 'booked'",
            (wash_id, wash_date, time_str, user_id)
        )
        existing = await cursor.fetchone()
        if existing:
            await callback.answer("Вы уже записаны на это время. Нельзя записаться дважды.", show_alert=True)
            return

        booked = False
        cursor = await conn.execute(
            "SELECT ws.id, ws.datetime, cw.name, cw.address, cw.phone, cw.admin_id "
            "FROM wash_slots ws JOIN car_washes cw ON ws.wash_id = cw.id "
            "WHERE ws.wash_id = ? AND date(ws.datetime) = ? AND strftime('%H:%M', ws.datetime) = ? AND ws.status = 'free'",
            (wash_id, wash_date, time_str)
        )
        slots = await cursor.fetchall()
        for slot_id, dt_str, wash_name, address, phone, admin_id in slots:
            update_cursor = await conn.execute(
                "UPDATE wash_slots SET status = 'booked', user_id = ?, progress = 'booked' WHERE id = ? AND status = 'free'",
                (user_id, slot_id)
            )
            if update_cursor.rowcount > 0:   # FIX: замена total_changes на rowcount
                booked = True
                await conn.commit()
                client_text = (
                    f"✅ Вы записаны на мойку '{wash_name}' на {dt_str}.\n\n"
                    f"📍 Адрес: {address or 'не указан'}\n"
                    f"📞 Телефон: {phone or 'не указан'}\n\n"
                    "Вам придёт напоминание за 1 час."
                )
                cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отменить запись", callback_data=f"cancel_booking_{slot_id}")]
                ])
                await callback.message.edit_text(client_text, reply_markup=cancel_kb)
                # Уведомление админу
                cursor2 = await conn.execute("SELECT phone FROM users WHERE telegram_id = ?", (user_id,))
                phone_row = await cursor2.fetchone()
                client_phone = phone_row[0] if phone_row else "не указан"
                admin_text = f"🚿 Новая запись: {wash_name}, {dt_str}\nКлиент: {client_phone}"
                await callback.bot.send_message(admin_id, admin_text)
                request_text = f"🚿 Новая запись на мойку\nМойка: {wash_name}\nВремя: {dt_str}"
                await notify_regional_admin(callback.bot, city, request_text)
                break
        if not booked:
            await callback.answer("К сожалению, все места на это время уже заняты. Попробуйте другое.", show_alert=True)
            return
    await state.clear()
    await callback.message.answer("Главное меню:", reply_markup=main_menu_kb('client'))
    await callback.answer()

# ========== ЭВАКУАТОР ==========
@router.message(F.text == "🚨 Эвакуатор")
async def tow_request(message: Message, state: FSMContext):
    user_id = message.from_user.id
    city = await get_user_city(user_id)
    if not city:
        await message.answer("Сначала выберите город в /start")
        return
    await state.update_data(city=city)
    await state.set_state(ClientStates.sending_tow_location)
    await message.answer(
        "📍 Отправьте вашу геолокацию, чтобы мы могли найти ближайших эвакуаторов:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📍 Отправить геолокацию", request_location=True)]],
            resize_keyboard=True, one_time_keyboard=True
        )
    )

@router.message(StateFilter(ClientStates.sending_tow_location), F.location)
async def tow_location_received(message: Message, state: FSMContext):
    lat = message.location.latitude
    lon = message.location.longitude
    await state.update_data(lat=lat, lon=lon)
    await state.set_state(ClientStates.choosing_tow_vehicle_type)
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🚗 Легковой")],
        [KeyboardButton(text="🚙 Внедорожник")],
        [KeyboardButton(text="🚚 Грузовой")],
    ], resize_keyboard=True, one_time_keyboard=True)
    await message.answer("Выберите тип авто:", reply_markup=kb)

@router.message(StateFilter(ClientStates.choosing_tow_vehicle_type), F.text.in_(["🚗 Легковой", "🚙 Внедорожник", "🚚 Грузовой"]))
async def tow_vehicle_type_chosen(message: Message, state: FSMContext):
    await state.update_data(vehicle_type=message.text)
    await state.set_state(ClientStates.choosing_tow_condition)
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="✅ На ходу")],
        [KeyboardButton(text="❌ Не на ходу")],
    ], resize_keyboard=True, one_time_keyboard=True)
    await message.answer("Выберите состояние авто:", reply_markup=kb)

@router.message(StateFilter(ClientStates.choosing_tow_condition), F.text.in_(["✅ На ходу", "❌ Не на ходу"]))
async def tow_condition_chosen(message: Message, state: FSMContext):
    await state.update_data(condition=message.text)
    await state.set_state(ClientStates.entering_tow_comment)
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="⏭ Пропустить")],
        [KeyboardButton(text="⬅ Назад")],
    ], resize_keyboard=True)
    await message.answer("Добавьте комментарий (или нажмите «Пропустить»):", reply_markup=kb)

@router.message(StateFilter(ClientStates.entering_tow_comment), F.text == "⏭ Пропустить")
async def tow_comment_skipped(message: Message, state: FSMContext):
    await state.update_data(comment="")
    await finalize_tow_request(message, state)

@router.message(StateFilter(ClientStates.entering_tow_comment), F.text == "⬅ Назад")
async def tow_comment_back(message: Message, state: FSMContext):
    await state.set_state(ClientStates.choosing_tow_condition)
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="✅ На ходу")],
        [KeyboardButton(text="❌ Не на ходу")],
    ], resize_keyboard=True, one_time_keyboard=True)
    await message.answer("Выберите состояние авто:", reply_markup=kb)

@router.message(StateFilter(ClientStates.entering_tow_comment), F.text & ~F.text.in_(["⏭ Пропустить", "⬅ Назад"]))
async def tow_comment_entered(message: Message, state: FSMContext):
    await state.update_data(comment=message.text)
    await finalize_tow_request(message, state)

async def finalize_tow_request(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id
    city = data['city']
    lat = data['lat']
    lon = data['lon']
    vehicle_type = data['vehicle_type']
    condition = data['condition']
    comment = data.get('comment', '')
    description = f"Тип: {vehicle_type}\nСостояние: {condition}\nКомментарий: {comment}"
    maps_link = f"https://maps.google.com/?q={lat},{lon}"
    full_description = f"{description}\n📍 [Открыть на карте]({maps_link})"

    async with db.session() as conn:
        request_service = RequestService(conn)
        request_id = await request_service.create_request(
            user_id=user_id,
            req_type='tow',
            city=city,
            description=full_description
        )
        sent_msg = await message.answer(
            f"✅ Ваша заявка на эвакуатор №{request_id} принята.\n\n{full_description}\n\n⏳ Ожидайте предложений.",
            parse_mode='Markdown'
        )
        await request_service.request_repo.update(request_id, {
            "client_chat_id": sent_msg.chat.id,
            "client_message_id": sent_msg.message_id
        })
        await conn.commit()

        await notify_regional_admin(message.bot, city, f"Новая заявка на эвакуатор #{request_id}")

        tow_repo = TowTruckRepository(conn)
        towers = await tow_repo.get_by_city(city)
        for tower in towers:
            try:
                await message.bot.send_message(
                    tower.admin_id,
                    f"🚨 Новая заявка на эвакуатор #{request_id}\n"
                    f"Город: {city}\n{full_description}\n\nПредложите цену:",
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="💰 Предложить цену", callback_data=f"tow_offer_{request_id}")]
                    ])
                )
            except Exception as e:
                print(f"Не удалось уведомить эвакуатора {tower.admin_id}: {e}")

    await state.clear()

@router.callback_query(F.data.startswith("choose_tow_off_"))
async def choose_tow_offer(callback: CallbackQuery):
    offer_id = int(callback.data.split("_")[3])
    async with db.session() as conn:
        cursor = await conn.execute("""
            SELECT o.request_id, o.price, t.name, t.phone, r.user_id, r.client_chat_id, r.client_message_id, t.admin_id,
                   u.full_name, u.phone
            FROM tow_offers o
            JOIN tow_trucks t ON o.tower_id = t.id
            JOIN requests r ON o.request_id = r.id
            JOIN users u ON r.user_id = u.telegram_id
            WHERE o.id = ?
        """, (offer_id,))
        row = await cursor.fetchone()
        if not row:
            await callback.answer("Предложение не найдено")
            return
        request_id, price, tow_name, tow_phone, client_id, chat_id, msg_id, tow_admin_id, client_full_name, client_phone = row

        await conn.execute("UPDATE tow_offers SET is_selected = 1 WHERE id = ?", (offer_id,))
        await conn.execute("UPDATE requests SET status = 'accepted', accepted_by = (SELECT tower_id FROM tow_offers WHERE id = ?) WHERE id = ?", (offer_id, request_id))
        await conn.commit()

    await callback.message.edit_text(
        f"✅ Вы выбрали предложение от {tow_name} на сумму {price} KZT.\n\n"
        f"📞 Телефон для связи: {tow_phone}\nСвяжитесь с эвакуатором."
    )

    status_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚗 В пути", callback_data=f"tow_status_{request_id}_in_progress")],
        [InlineKeyboardButton(text="📍 На месте", callback_data=f"tow_status_{request_id}_on_site")],
        [InlineKeyboardButton(text="✅ Выполнено", callback_data=f"tow_status_{request_id}_completed")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"tow_status_{request_id}_cancelled")]
    ])
    await callback.bot.send_message(
        tow_admin_id,
        f"✅ Ваше предложение по заявке #{request_id} выбрано клиентом!\n\n"
        f"💰 Сумма: {price} KZT\nКонтакты клиента:\nИмя: {client_full_name or 'не указано'}\n📞 Телефон: {client_phone or 'не указан'}\n\nУправляйте статусом:",
        reply_markup=status_kb
    )
    await callback.answer()

# ========== АВТОПОМОЩЬ ==========
ROADSIDE_SERVICES = [
    ('locksmith', '🔓 Вскрытие замков'),
    ('tire', '🛞 Выездной шиномонтаж'),
    ('delivery', '📦 Доставка запчастей'),
    ('electrician', '⚡ Автоэлектрик'),
    ('mechanic', '🔧 Мастер-универсал'),
]

@router.message(F.text == "🆘 Автопомощь")
async def roadside_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    city = await get_user_city(user_id)
    if not city:
        await message.answer("Сначала выберите город в /start")
        return
    await state.update_data(city=city)
    await state.set_state(ClientStates.choosing_roadside_services)
    await message.answer(
        "Выберите одну или несколько услуг, которые вам нужны:",
        reply_markup=roadside_services_kb(ROADSIDE_SERVICES, [])
    )

@router.callback_query(StateFilter(ClientStates.choosing_roadside_services), F.data.startswith("roadside_toggle_"))
async def roadside_toggle(callback: CallbackQuery, state: FSMContext):
    service_id = callback.data.split("_")[2]
    data = await state.get_data()
    selected = data.get('selected_services', [])
    if service_id in selected:
        selected.remove(service_id)
    else:
        selected.append(service_id)
    await state.update_data(selected_services=selected)
    await callback.message.edit_reply_markup(
        reply_markup=roadside_services_kb(ROADSIDE_SERVICES, selected)
    )
    await callback.answer()

@router.callback_query(StateFilter(ClientStates.choosing_roadside_services), F.data == "roadside_done")
async def roadside_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get('selected_services', [])
    if not selected:
        await callback.answer("Выберите хотя бы одну услугу!", show_alert=True)
        return
    await state.set_state(ClientStates.sending_roadside_location)
    await delete_message(callback)
    await callback.message.answer(
        "📍 Отправьте вашу геолокацию (кнопка ниже) или напишите адрес, где требуется помощь:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📍 Отправить геолокацию", request_location=True)]],
            resize_keyboard=True
        )
    )
    await callback.answer()

@router.callback_query(StateFilter(ClientStates.choosing_roadside_services), F.data == "roadside_back")
async def roadside_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await delete_message(callback)
    await callback.message.answer("Главное меню:", reply_markup=main_menu_kb('client'))
    await callback.answer()

@router.message(StateFilter(ClientStates.sending_roadside_location), F.location)
async def roadside_location_received(message: Message, state: FSMContext):
    lat = message.location.latitude
    lon = message.location.longitude
    await state.update_data(lat=lat, lon=lon)
    await state.set_state(ClientStates.entering_roadside_description)
    await message.answer(
        "📝 Опишите, какая помощь нужна:",
        reply_markup=back_kb()
    )

@router.message(StateFilter(ClientStates.sending_roadside_location), F.text)
async def roadside_address_received(message: Message, state: FSMContext):
    await state.update_data(address=message.text)
    await state.set_state(ClientStates.entering_roadside_description)
    await message.answer(
        "📝 Опишите, какая помощь нужна:",
        reply_markup=back_kb()
    )

@router.message(StateFilter(ClientStates.entering_roadside_description), F.text.in_(["⬅ Назад", "/назад"]))
async def roadside_description_back(message: Message, state: FSMContext):
    await state.set_state(ClientStates.sending_roadside_location)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Отправить геолокацию", request_location=True)]],
        resize_keyboard=True
    )
    await delete_message(message)
    await message.answer(
        "📍 Отправьте вашу геолокацию (кнопка ниже) или напишите адрес:",
        reply_markup=kb
    )

@router.message(StateFilter(ClientStates.entering_roadside_description), F.text & ~F.text.in_(["⬅ Назад", "/назад"]))
async def roadside_description_entered(message: Message, state: FSMContext):
    desc = message.text
    await state.update_data(description=desc)
    await finalize_roadside_requests(message, state)

async def finalize_roadside_requests(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id
    city = data['city']
    selected_services = data.get('selected_services', [])
    lat = data.get('lat')
    lon = data.get('lon')
    address = data.get('address')
    description = data['description']

    full_description = description
    geo_part = ""
    if lat and lon:
        maps_link = f"https://maps.google.com/?q={lat},{lon}"
        geo_part = f"📍 [Геолокация]({maps_link})"
    elif address:
        geo_part = f"📍 Адрес: {address}"
    if geo_part:
        full_description += f"\n{geo_part}"

    service_names = dict(ROADSIDE_SERVICES)
    created_any = False
    no_providers_services = []

    async with db.session() as conn:
        for service in selected_services:
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM service_providers WHERE city_id = (SELECT id FROM cities WHERE name = ?) AND service_type = ?",
                (city, service)
            )
            count = await cursor.fetchone()
            if count[0] == 0:
                no_providers_services.append(service_names.get(service, service))
                continue

            cursor = await conn.execute(
                "INSERT INTO requests (user_id, type, service_subtype, city, description, status, created_at) VALUES (?, 'urgent', ?, ?, ?, 'new', ?)",
                (user_id, service, city, full_description, datetime.now().isoformat())
            )
            request_id = cursor.lastrowid
            sent_msg = await message.answer(
                f"✅ Ваша заявка №{request_id} на услугу «{service_names.get(service, service)}» принята.\n\n{full_description}\n\n⏳ Ожидайте предложений.",
                parse_mode='Markdown'
            )
            await conn.execute(
                "UPDATE requests SET client_chat_id = ?, client_message_id = ? WHERE id = ?",
                (sent_msg.chat.id, sent_msg.message_id, request_id)
            )
            cursor = await conn.execute(
                "SELECT admin_id FROM service_providers WHERE city_id = (SELECT id FROM cities WHERE name = ?) AND service_type = ?",
                (city, service)
            )
            providers = await cursor.fetchall()
            for (provider_id,) in providers:
                try:
                    await message.bot.send_message(
                        provider_id,
                        f"🆘 Новая заявка #{request_id} на услугу «{service_names.get(service, service)}»\n"
                        f"Город: {city}\n{full_description}\n\nПредложите цену:",
                        parse_mode='Markdown',
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="💰 Предложить цену", callback_data=f"urgent_offer_{request_id}")]
                        ])
                    )
                except Exception as e:
                    print(f"Не удалось уведомить специалиста {provider_id}: {e}")
            created_any = True
        await conn.commit()

    if created_any:
        services_str = ", ".join([service_names.get(s, s) for s in selected_services if s not in no_providers_services])
        await notify_regional_admin(message.bot, city, f"🆘 Новая заявка на автопомощь (услуги: {services_str})\n{description}")

    if no_providers_services:
        services_list = "\n".join([f"• {s}" for s in no_providers_services])
        marketing_text = (
            f"📢 *По выбранным вами категориям пока нет зарегистрированных специалистов:*\n"
            f"{services_list}\n\n"
            f"🚀 Но не переживайте! Вы можете ускорить появление мастеров в нашем сервисе. "
            f"Поделитесь ссылкой на бота с вашими знакомыми мастерами или с теми, кто мог бы выполнить эту работу. "
            f"Чем больше специалистов зарегистрируется, тем быстрее вы найдёте исполнителя!\n\n"
            f"🔗 *Ссылка для приглашения:* https://t.me/C_disk_avto_24_bot?start=referral\n\n"
            f"✨ А для специалистов: регистрация в AvtoMaster24 — это новые клиенты без рекламы, удобный график и честные заказы. "
            f"Расскажите им, как это выгодно!"
        )
        await message.answer(marketing_text, parse_mode='Markdown')

    if created_any:
        await message.answer(
            "✅ Заявки по доступным услугам отправлены специалистам.\n\n"
            "📋 Пожалуйста, просмотрите предложения выше (они появляются в первых сообщениях по каждой услуге) и выберите одно, нажав на соответствующую кнопку.\n\n"
            "⚠️ Важно: новые предложения от специалистов будут поступать до тех пор, пока вы не сделаете выбор. Как только вы выберете исполнителя, приём заявок по этой услуге прекратится."
        )
    else:
        await message.answer("😕 К сожалению, по выбранным вами услугам пока нет зарегистрированных специалистов. Попробуйте позже или пригласите мастеров.")

    await state.clear()

@router.callback_query(F.data.startswith("choose_roadside_off_"))
async def choose_roadside_offer(callback: CallbackQuery, state: FSMContext):
    offer_id = int(callback.data.split("_")[3])
    async with db.session() as conn:
        cursor = await conn.execute("""
            SELECT o.request_id, o.price, s.name, s.phone, r.user_id, r.client_chat_id, r.client_message_id, s.admin_id,
                   u.full_name, u.phone
            FROM roadside_offers o
            JOIN suppliers s ON o.specialist_id = s.id
            JOIN requests r ON o.request_id = r.id
            JOIN users u ON r.user_id = u.telegram_id
            WHERE o.id = ?
        """, (offer_id,))
        row = await cursor.fetchone()
        if not row:
            await callback.answer("Предложение не найдено")
            return
        request_id, price, sp_name, sp_phone, client_id, chat_id, msg_id, sp_admin_id, client_full_name, client_phone = row

        await conn.execute("UPDATE roadside_offers SET is_selected = 1 WHERE id = ?", (offer_id,))
        await conn.execute("UPDATE requests SET status = 'accepted', accepted_by = (SELECT specialist_id FROM roadside_offers WHERE id = ?) WHERE id = ?", (offer_id, request_id))
        await conn.commit()

    await callback.message.edit_text(
        f"✅ Вы выбрали предложение от {sp_name} на сумму {price} KZT.\n\n"
        f"📞 Телефон для связи: {sp_phone}\nСвяжитесь со специалистом."
    )

    status_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚗 В пути", callback_data=f"roadside_status_{request_id}_in_progress")],
        [InlineKeyboardButton(text="📍 На месте", callback_data=f"roadside_status_{request_id}_on_site")],
        [InlineKeyboardButton(text="✅ Выполнено", callback_data=f"roadside_status_{request_id}_completed")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"roadside_status_{request_id}_cancelled")]
    ])
    await callback.bot.send_message(
        sp_admin_id,
        f"✅ Ваше предложение по заявке #{request_id} выбрано клиентом!\n\n"
        f"💰 Сумма: {price} KZT\nКонтакты клиента:\nИмя: {client_full_name or 'не указано'}\n📞 Телефон: {client_phone or 'не указан'}\n\nУправляйте статусом:",
        reply_markup=status_kb
    )
    await callback.answer()

# ========== ЗАПЧАСТИ (тендер) ==========
@router.message(F.text == "🛒 Запчасти")
async def parts_menu(message: Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔍 Найти З/Ч во всех магазинах города")],
        [KeyboardButton(text="⬅ Главное меню")]
    ], resize_keyboard=True)
    await message.answer("Выберите действие:", reply_markup=kb)
    await state.set_state(ClientStates.choosing_part_search_type)

@router.message(StateFilter(ClientStates.choosing_part_search_type), F.text == "🔍 Найти З/Ч во всех магазинах города")
async def part_request_start(message: Message, state: FSMContext):
    await state.set_state(ClientStates.entering_part_request_name)
    await message.answer(
        "Введите название нужной запчасти (или артикул):",
        reply_markup=back_kb()
    )

@router.message(StateFilter(ClientStates.entering_part_request_name))
async def part_request_name(message: Message, state: FSMContext):
    part_name = message.text
    await state.update_data(part_name=part_name)
    await state.set_state(ClientStates.entering_part_request_car)
    await message.answer(
        "Укажите марку и модель авто (например, Toyota Camry 2012) или отправьте /пропустить:",
        reply_markup=back_kb()
    )

@router.message(StateFilter(ClientStates.entering_part_request_car))
async def part_request_car(message: Message, state: FSMContext):
    car_info = message.text if message.text != "/пропустить" else ""
    await state.update_data(car_info=car_info)
    await state.set_state(ClientStates.entering_part_request_comment)
    await message.answer(
        "Добавьте комментарий (например, состояние, срочность) или /пропустить:",
        reply_markup=back_kb()
    )

@router.message(StateFilter(ClientStates.entering_part_request_comment))
async def part_request_comment(message: Message, state: FSMContext):
    comment = message.text if message.text != "/пропустить" else ""
    await create_part_request(message, state, comment)

async def create_part_request(message: Message, state: FSMContext, comment: str):
    data = await state.get_data()
    user_id = message.from_user.id
    part_name = data['part_name']
    car_info = data.get('car_info', '')
    city = await get_user_city(user_id)
    if not city:
        await message.answer("Сначала выберите город в /start")
        await state.clear()
        return

    async with db.session() as conn:
        cursor = await conn.execute(
            "INSERT INTO part_requests (user_id, city, part_name, car_info, comment, status, created_at) VALUES (?, ?, ?, ?, ?, 'new', ?)",
            (user_id, city, part_name, car_info, comment, datetime.now().isoformat())
        )
        request_id = cursor.lastrowid
        text = (
            f"✅ Ваш запрос на запчасть №{request_id} принят.\n\n"
            f"🔧 Деталь: {part_name}\n"
            f"🚗 Авто: {car_info if car_info else 'не указано'}\n"
            f"📝 Комментарий: {comment if comment else 'нет'}\n\n"
            "⏳ Ожидайте предложений от поставщиков. Как только появятся новые предложения, они отобразятся здесь."
        )
        sent_msg = await message.answer(text, reply_markup=cancel_part_request_kb(request_id))
        await conn.execute(
            "UPDATE part_requests SET client_chat_id = ?, client_message_id = ? WHERE id = ?",
            (sent_msg.chat.id, sent_msg.message_id, request_id)
        )
        await conn.commit()
        await state.set_state(ClientStates.waiting_for_part_offers)
        await state.update_data(part_request_id=request_id)

        await notify_regional_admin(message.bot, city, f"📦 Новый запрос запчасти #{request_id}\nДеталь: {part_name}\nАвто: {car_info if car_info else 'не указано'}")

        cursor = await conn.execute(
            "SELECT u.telegram_id FROM users u JOIN suppliers s ON u.telegram_id = s.admin_id WHERE u.role = 'supplier' AND u.city = ?",
            (city,)
        )
        suppliers = await cursor.fetchall()
        for (supplier_id,) in suppliers:
            try:
                await message.bot.send_message(
                    supplier_id,
                    f"📢 Новый запрос на запчасть #{request_id}\n"
                    f"Деталь: {part_name}\n"
                    f"Авто: {car_info if car_info else 'не указано'}\n"
                    f"Комментарий: {comment if comment else 'нет'}\n"
                    "Предложите цену:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="💰 Предложить цену", callback_data=f"part_offer_{request_id}")]
                    ])
                )
            except Exception as e:
                print(f"Не удалось уведомить поставщика {supplier_id}: {e}")

@router.callback_query(F.data.startswith("part_offer_"))
async def part_offer_price(callback: CallbackQuery, state: FSMContext):
    request_id = int(callback.data.split("_")[2])
    await state.update_data(request_id=request_id)
    await state.set_state(ClientStates.entering_price_for_part_offer)
    await callback.message.answer("Введите вашу цену (в KZT):")
    await callback.answer()

@router.message(StateFilter(ClientStates.entering_price_for_part_offer))
async def part_offer_price_entered(message: Message, state: FSMContext):
    try:
        price = int(message.text)
    except ValueError:
        await message.answer("Введите число.")
        return
    data = await state.get_data()
    request_id = data['request_id']
    user_id = message.from_user.id
    async with db.session() as conn:
        cursor = await conn.execute("SELECT id FROM suppliers WHERE admin_id = ?", (user_id,))
        supplier = await cursor.fetchone()
        if not supplier:
            await message.answer("Вы не зарегистрированы как поставщик.")
            await state.clear()
            return
        supplier_id = supplier[0]
        await conn.execute(
            "INSERT INTO part_offers (request_id, supplier_id, price, comment, created_at) VALUES (?, ?, ?, ?, ?)",
            (request_id, supplier_id, price, "", datetime.now().isoformat())
        )
        await conn.commit()
    await message.answer("✅ Ваше предложение отправлено клиенту.")
    await state.clear()

# ========== ИСТОРИЯ ЗАЯВОК ==========
@router.message(F.text == "📊 История заявок")
async def show_history(message: Message):
    user_id = message.from_user.id
    async with db.session() as conn:
        request_repo = RequestRepository(conn)
        requests = await request_repo.get_by_user_id(user_id, limit=20)
    if not requests:
        await message.answer("У вас пока нет заявок.")
        return
    status_emoji = {
        'new': '🆕', 'accepted': '✅', 'in_progress': '🔧',
        'completed': '✔️', 'cancelled': '❌', 'problem_not_resolved': '⚠️'
    }
    text = "📋 Ваши последние заявки:\n\n"
    for req in requests:
        emoji = status_emoji.get(req.status, '❓')
        date_str = req.created_at[:16] if req.created_at else ""
        text += f"{emoji} #{req.id} – {req.type} от {date_str}\n"
        text += f"{req.description[:60]}...\n\n"
    await message.answer(text)

# ========== СЕРВИСНАЯ КНИЖКА ==========
@router.message(F.text == "📒 Сервисная книжка")
async def service_book_menu(message: Message, state: FSMContext):
    user_id = message.from_user.id
    async with db.session() as conn:
        cursor = await conn.execute("SELECT id, brand, model, year, license_plate FROM user_cars WHERE user_id = ?", (user_id,))
        cars = await cursor.fetchall()
    if not cars:
        await message.answer(
            "У вас пока нет добавленных автомобилей. Хотите добавить?",
            reply_markup=ReplyKeyboardMarkup(keyboard=[
                [KeyboardButton(text="➕ Добавить авто")],
                [KeyboardButton(text="⬅ Главное меню")]
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
        cursor = await conn.execute("SELECT brand, model, year, license_plate FROM user_cars WHERE id = ?", (car_id,))
        car = await cursor.fetchone()
        if not car:
            await callback.answer("Автомобиль не найден")
            return
        brand, model, year, plate = car
        cursor = await conn.execute("SELECT date, mileage, description, service_type, cost FROM service_records WHERE car_id = ? ORDER BY date DESC", (car_id,))
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
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить запись", callback_data=f"add_record_{car_id}")],
        [InlineKeyboardButton(text="⬅ К списку авто", callback_data="back_to_cars")]
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
        await conn.execute(
            "INSERT INTO service_records (user_id, car_id, date, mileage, description, service_type, cost) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, car_id, date, mileage, desc, 'manual', cost_int)
        )
        await conn.commit()
    await message.answer("✅ Запись добавлена в сервисную книжку.")
    await state.clear()
    await service_book_menu(message, state)

@router.callback_query(F.data == "back_to_cars")
async def back_to_cars(callback: CallbackQuery, state: FSMContext):
    await service_book_menu(callback.message, state)
    await callback.answer()

# ========== МОИ ОТЗЫВЫ ==========
@router.message(F.text == "⭐ Мои отзывы")
async def show_my_reviews(message: Message):
    user_id = message.from_user.id
    async with db.session() as conn:
        cursor = await conn.execute("SELECT id, entity_type, rating, comment, created_at FROM reviews WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
        reviews = await cursor.fetchall()
    if not reviews:
        await message.answer("Вы ещё не оставляли отзывов.")
        return
    text = "⭐ Ваши отзывы:\n\n"
    for rev in reviews:
        rev_id, etype, rating, comment, created_at = rev
        date_str = created_at[:10] if created_at else ""
        stars = "⭐" * rating
        comment_display = comment if comment else "(нет комментария)"
        text += f"{stars} ({rating}/5) на {etype} от {date_str}\n"
        text += f"   «{comment_display}»\n\n"
    await message.answer(text)

# ========== ОБРАБОТЧИК ТЕКСТОВОГО ОТЗЫВА ==========
@router.message(StateFilter(ClientStates.waiting_for_review_text))
async def process_review_text(message: Message, state: FSMContext):
    data = await state.get_data()
    review_id = data.get('review_id')
    if not review_id:
        await message.answer("Ошибка: не найден отзыв. Попробуйте ещё раз.")
        await state.clear()
        return
    comment = message.text
    if comment == "/пропустить":
        comment = ""

    async with db.session() as conn:
        await conn.execute(
            "UPDATE reviews SET comment = ? WHERE id = ?",
            (comment, review_id)
        )
        await conn.commit()

        cursor = await conn.execute(
            "SELECT entity_type, entity_id, rating FROM reviews WHERE id = ?",
            (review_id,)
        )
        row = await cursor.fetchone()
        if row:
            etype, eid, rating = row
            await notify_regional_admin_about_review(message.bot, etype, eid, rating, comment)

    await message.answer("Спасибо за ваш отзыв! Он будет опубликован после проверки модератором.")
    await state.clear()
    role = await get_user_role(message.from_user.id)
    await message.answer("Главное меню:", reply_markup=main_menu_kb(role))

# ========== ПРОСМОТР ОТЗЫВОВ (С ПОДДЕРЖКОЙ СТАРЫХ ТИПОВ) ==========
@router.callback_query(F.data.startswith("view_reviews_"))
async def view_reviews_handler(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer("Неверный формат данных")
        return
    try:
        entity_id = int(parts[-1])
    except ValueError:
        await callback.answer("Неверный ID объекта")
        return
    entity_type = "_".join(parts[2:-1])
    await show_reviews(callback.message, entity_type, entity_id, 0, state, edit=False)
    await callback.answer()

@router.callback_query(F.data.startswith("view_reviews_page_"))
async def view_reviews_page_handler(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    if len(parts) < 5:
        await callback.answer("Неверный формат данных")
        return
    try:
        page = int(parts[-1])
        entity_id = int(parts[-2])
    except ValueError:
        await callback.answer("Неверный номер страницы или ID")
        return
    entity_type = "_".join(parts[3:-2])
    await show_reviews(callback.message, entity_type, entity_id, page, state, edit=True)
    await callback.answer()

async def show_reviews(message: types.Message, entity_type: str, entity_id: int, page: int, state: FSMContext, edit: bool = False):
    limit = 5
    offset = page * limit

    # Определяем возможные entity_type в БД (учитываем старые и новые)
    possible_types = [entity_type]
    if entity_type == 'sto':
        possible_types.append('station')
    elif entity_type == 'station':
        possible_types.append('sto')
    elif entity_type == 'car_wash':
        possible_types.append('wash')
    elif entity_type == 'tow_truck':
        possible_types.append('tow')
    elif entity_type == 'service_provider':
        possible_types.append('service')
    # Для других типов оставляем как есть

    placeholders = ','.join('?' for _ in possible_types)

    async with db.session() as conn:
        cursor = await conn.execute(
            f"SELECT COUNT(*) FROM reviews WHERE entity_type IN ({placeholders}) AND entity_id = ?",
            (*possible_types, entity_id)
        )
        total = (await cursor.fetchone())[0]

        if total == 0:
            text = "😕 На этот объект пока нет отзывов."
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
            ])
            if edit:
                await message.edit_text(text, reply_markup=kb)
            else:
                await message.answer(text, reply_markup=kb)
            return

        cursor = await conn.execute(f"""
            SELECT r.rating, r.comment, r.created_at, u.full_name, u.display_name_choice
            FROM reviews r
            JOIN users u ON r.user_id = u.telegram_id
            WHERE r.entity_type IN ({placeholders}) AND r.entity_id = ?
            ORDER BY r.created_at DESC
            LIMIT ? OFFSET ?
        """, (*possible_types, entity_id, limit, offset))
        reviews = await cursor.fetchall()

    total_pages = (total - 1) // limit + 1
    text = f"⭐ Отзывы (страница {page+1} из {total_pages}):\n\n"
    for rating, comment, created_at, full_name, display_choice in reviews:
        stars = stars_from_rating(rating)
        date_str = created_at[:10] if created_at else ""
        if display_choice == 'real_name' and full_name:
            name = full_name
        else:
            name = "Пользователь"
        text += f"{stars} {date_str} – {name}\n"
        if comment:
            text += f"   «{comment}»\n"
        text += "\n"

    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"view_reviews_page_{entity_type}_{entity_id}_{page-1}"))
    if page + 1 < total_pages:
        buttons.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"view_reviews_page_{entity_type}_{entity_id}_{page+1}"))
    kb_buttons = [buttons] if buttons else []
    back_button = InlineKeyboardButton(text="⬅ К объекту", callback_data=f"back_to_{entity_type}_{entity_id}")
    kb_buttons.append([back_button])
    kb_buttons.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)

    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)

    await state.update_data(last_entity_type=entity_type, last_entity_id=entity_id)

# ---------- Обработчик возврата к карточке объекта ----------
@router.callback_query(F.data.startswith("back_to_"))
async def back_to_object(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    if len(parts) < 3:
        await callback.answer("Неверный формат данных")
        return
    entity_type = parts[2]
    try:
        entity_id = int(parts[3])
    except (IndexError, ValueError):
        await callback.answer("Неверный ID объекта")
        return

    if entity_type in ('sto', 'station'):
        await show_station_card_by_id(callback.message, entity_id, state, edit=True)
        await state.set_state(ClientStates.viewing_station)
    elif entity_type == 'car_wash':
        await show_wash_card_by_id(callback.message, entity_id, state, edit=True)
        await state.set_state(ClientStates.viewing_wash)
    elif entity_type == 'tow':
        await show_tow_card_by_id(callback.message, entity_id, state, edit=True)
        await state.set_state(ClientStates.viewing_tow)
    elif entity_type == 'supplier':
        await show_supplier_card_by_id(callback.message, entity_id, state, edit=True)
        await state.set_state(ClientStates.viewing_supplier)
    elif entity_type == 'service_provider':
        await show_service_card_by_id(callback.message, entity_id, state, edit=True)
        await state.set_state(ClientStates.viewing_service)
    else:
        await callback.answer("Неизвестный тип объекта")
    await callback.answer()

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ КАРТОЧЕК ==========
async def show_station_card_by_id(message: types.Message, station_id: int, state: FSMContext, edit: bool = False):
    async with db.session() as conn:
        station_repo = StationRepository(conn)
        station = await station_repo.get_by_id(station_id)
        if not station:
            if edit:
                await message.edit_text("СТО не найдено")
            else:
                await message.answer("СТО не найдено")
            return
        stars = stars_from_rating(station.rating or 0)
        text = (
            f"🏢 {station.name}\n"
            f"⭐ Рейтинг: {stars} ({station.rating:.1f} на основе {station.reviews_count} отзывов)\n"
            f"📍 Адрес: {station.address or 'не указан'}\n"
            f"📞 Телефон: {station.phone or 'не указан'}\n\n"
            "Выберите действие:"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Выбрать это СТО", callback_data=f"select_sto_{station_id}")],
            [InlineKeyboardButton(text="⭐ Посмотреть отзывы", callback_data=f"view_reviews_sto_{station_id}")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
        ])
        if edit:
            await message.edit_text(text, reply_markup=kb)
        else:
            await message.answer(text, reply_markup=kb)
        await state.update_data(station_id=station_id)
        await state.set_state(ClientStates.viewing_station)

async def show_wash_card_by_id(message: types.Message, wash_id: int, state: FSMContext, edit: bool = False):
    async with db.session() as conn:
        wash_repo = CarWashRepository(conn)
        wash = await wash_repo.get_by_id(wash_id)
        if not wash:
            if edit:
                await message.edit_text("Мойка не найдена")
            else:
                await message.answer("Мойка не найдена")
            return
        stars = stars_from_rating(wash.rating or 0)
        text = (
            f"🚿 {wash.name}\n"
            f"⭐ Рейтинг: {stars} ({wash.rating:.1f} на основе {wash.reviews_count} отзывов)\n"
            f"📍 Адрес: {wash.address or 'не указан'}\n"
            f"📞 Телефон: {wash.phone or 'не указан'}\n"
            f"🚗 Количество боксов: {wash.boxes}\n"
            f"⏱ Длительность услуги: {wash.slot_duration} мин\n\n"
            "Выберите действие:"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Записаться", callback_data=f"book_wash_{wash_id}")],
            [InlineKeyboardButton(text="⭐ Посмотреть отзывы", callback_data=f"view_reviews_car_wash_{wash_id}")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
        ])
        if edit:
            await message.edit_text(text, reply_markup=kb)
        else:
            await message.answer(text, reply_markup=kb)
        await state.update_data(wash_id=wash_id)
        await state.set_state(ClientStates.viewing_wash)

async def show_tow_card_by_id(message: types.Message, tow_id: int, state: FSMContext, edit: bool = False):
    async with db.session() as conn:
        tow_repo = TowTruckRepository(conn)
        tow = await tow_repo.get_by_id(tow_id)
        if not tow:
            if edit:
                await message.edit_text("Эвакуатор не найден")
            else:
                await message.answer("Эвакуатор не найден")
            return
        stars = stars_from_rating(tow.rating or 0)
        text = (
            f"🚨 {tow.name}\n"
            f"⭐ Рейтинг: {stars} ({tow.rating:.1f} на основе {tow.reviews_count} отзывов)\n"
            f"📍 Адрес: {tow.address or 'не указан'}\n"
            f"📞 Телефон: {tow.phone or 'не указан'}\n\n"
            "Выберите действие:"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Заказать", callback_data=f"order_tow_{tow_id}")],
            [InlineKeyboardButton(text="⭐ Посмотреть отзывы", callback_data=f"view_reviews_tow_{tow_id}")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
        ])
        if edit:
            await message.edit_text(text, reply_markup=kb)
        else:
            await message.answer(text, reply_markup=kb)
        await state.update_data(tow_id=tow_id)
        await state.set_state(ClientStates.viewing_tow)

async def show_supplier_card_by_id(message: types.Message, supplier_id: int, state: FSMContext, edit: bool = False):
    async with db.session() as conn:
        supplier_repo = SupplierRepository(conn)
        supplier = await supplier_repo.get_by_id(supplier_id)
        if not supplier:
            if edit:
                await message.edit_text("Поставщик не найден")
            else:
                await message.answer("Поставщик не найден")
            return
        type_names = {'shop':'🏪 Магазин', 'dismantler':'🔧 Разборка', 'installer':'🔨 Установщик'}
        type_display = type_names.get(supplier.type, supplier.type)
        stars = stars_from_rating(supplier.rating or 0)
        text = (
            f"📦 {supplier.name}\n"
            f"Тип: {type_display}\n"
            f"⭐ Рейтинг: {stars} ({supplier.rating:.1f} на основе {supplier.reviews_count} отзывов)\n"
            f"📍 Адрес: {supplier.address or 'не указан'}\n"
            f"📞 Телефон: {supplier.phone or 'не указан'}\n\n"
            "Выберите действие:"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Перейти к товарам", callback_data=f"supplier_parts_{supplier_id}")],
            [InlineKeyboardButton(text="⭐ Посмотреть отзывы", callback_data=f"view_reviews_supplier_{supplier_id}")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
        ])
        if edit:
            await message.edit_text(text, reply_markup=kb)
        else:
            await message.answer(text, reply_markup=kb)
        await state.update_data(supplier_id=supplier_id)
        await state.set_state(ClientStates.viewing_supplier)

async def show_service_card_by_id(message: types.Message, service_id: int, state: FSMContext, edit: bool = False):
    async with db.session() as conn:
        provider_repo = ServiceProviderRepository(conn)
        provider = await provider_repo.get_by_id(service_id)
        if not provider:
            if edit:
                await message.edit_text("Специалист не найден")
            else:
                await message.answer("Специалист не найден")
            return
        service_names = {
            'locksmith': '🔓 Вскрытие замков',
            'tire': '🛞 Выездной шиномонтаж',
            'delivery': '📦 Доставка запчастей',
            'electrician': '⚡ Автоэлектрик',
            'mechanic': '🔧 Мастер-универсал'
        }
        service_display = service_names.get(provider.service_type, provider.service_type)
        stars = stars_from_rating(provider.rating or 0)
        text = (
            f"🆘 {provider.name}\n"
            f"Услуга: {service_display}\n"
            f"⭐ Рейтинг: {stars} ({provider.rating:.1f} на основе {provider.reviews_count} отзывов)\n"
            f"📍 Адрес: {provider.address or 'не указан'}\n"
            f"📞 Телефон: {provider.phone or 'не указан'}\n\n"
            "Выберите действие:"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Заказать", callback_data=f"order_service_{service_id}")],
            [InlineKeyboardButton(text="⭐ Посмотреть отзывы", callback_data=f"view_reviews_service_{service_id}")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
        ])
        if edit:
            await message.edit_text(text, reply_markup=kb)
        else:
            await message.answer(text, reply_markup=kb)
        await state.update_data(service_id=service_id)
        await state.set_state(ClientStates.viewing_service)

# ========== ГЛОБАЛЬНЫЙ ОБРАБОТЧИК ТЕКСТОВОЙ КНОПКИ "ОТМЕНА" ==========
@router.message(F.text == "❌ Отмена")
async def global_cancel(message: Message, state: FSMContext):
    await state.clear()
    await delete_message(message)
    role = await get_user_role(message.from_user.id)
    await message.answer("Действие отменено.", reply_markup=main_menu_kb(role))