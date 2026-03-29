# handlers/urgent.py
import logging
from datetime import datetime
from aiogram import Router, F, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

from database import db
from repositories.service_provider_repo import ServiceProviderRepository
from repositories.request_repo import RequestRepository
from states.client_states import UrgentServicesStates, ClientStates
from keyboards.reply import main_menu_kb, back_kb
from utils.helpers import notify_regional_admin, update_urgent_offers_message, stars_from_rating  # FIX: добавлен notify_regional_admin

logger = logging.getLogger(__name__)
router = Router()

SERVICE_NAMES = {
    'locksmith': '🔓 Вскрытие замков',
    'tire': '🛞 Выездной шиномонтаж',
    'delivery': '📦 Доставка запчастей',
    'electrician': '⚡ Автоэлектрик',
    'mechanic': '🔧 Мастер-универсал'
}

async def get_user_city(user_id: int) -> str | None:
    async with db.session() as conn:
        cursor = await conn.execute("SELECT city FROM users WHERE telegram_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else None


# ========== Клиентские обработчики ==========
@router.message(F.text.in_(["🔓 Вскрытие замков", "🛞 Выездной шиномонтаж", "📦 Доставка запчастей", "⚡ Автоэлектрик", "🔧 Мастер-универсал"]))
async def urgent_start(message: Message, state: FSMContext):
    service_map = {
        "🔓 Вскрытие замков": "locksmith",
        "🛞 Выездной шиномонтаж": "tire",
        "📦 Доставка запчастей": "delivery",
        "⚡ Автоэлектрик": "electrician",
        "🔧 Мастер-универсал": "mechanic"
    }
    service_type = service_map[message.text]
    user_id = message.from_user.id
    city = await get_user_city(user_id)
    if not city:
        await message.answer("Сначала выберите город в /start")
        return
    await state.update_data(city=city, service_type=service_type)
    await state.set_state(UrgentServicesStates.sending_location)

    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Отправить геолокацию", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer(
        f"{SERVICE_NAMES[service_type]}\n\n📍 Отправьте вашу геолокацию (или напишите адрес), чтобы мы могли найти ближайших специалистов:",
        reply_markup=kb
    )


@router.message(StateFilter(UrgentServicesStates.sending_location), F.location)
async def urgent_location_received(message: Message, state: FSMContext):
    lat = message.location.latitude
    lon = message.location.longitude
    await state.update_data(lat=lat, lon=lon)
    await state.set_state(UrgentServicesStates.entering_description)
    await message.answer(
        "📝 Опишите, что случилось (например, 'сломался ключ в замке', 'нужна замена колела'):",
        reply_markup=back_kb()
    )


@router.message(StateFilter(UrgentServicesStates.sending_location), F.text)
async def urgent_address_received(message: Message, state: FSMContext):
    await state.update_data(address=message.text)
    await state.set_state(UrgentServicesStates.entering_description)
    await message.answer(
        "📝 Опишите, что случилось:",
        reply_markup=back_kb()
    )


@router.message(StateFilter(UrgentServicesStates.entering_description), F.text.in_(["⬅ Назад", "/назад"]))
async def urgent_description_back(message: Message, state: FSMContext):
    await state.set_state(UrgentServicesStates.sending_location)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Отправить геолокацию", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    data = await state.get_data()
    service_type = data.get('service_type', 'услуга')
    await message.answer(
        f"{SERVICE_NAMES.get(service_type, service_type)}\n\n📍 Отправьте вашу геолокацию (или напишите адрес):",
        reply_markup=kb
    )


@router.message(StateFilter(UrgentServicesStates.entering_description), F.text & ~F.text.in_(["⬅ Назад", "/назад"]))
async def urgent_description_entered(message: Message, state: FSMContext):
    description = message.text
    await state.update_data(description=description)
    await finalize_urgent_request(message, state)


async def finalize_urgent_request(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id
    service_type = data['service_type']
    city = data['city']
    lat = data.get('lat')
    lon = data.get('lon')
    address = data.get('address')
    description = data['description']

    full_description = description
    if lat and lon:
        maps_link = f"https://maps.google.com/?q={lat},{lon}"
        full_description += f"\n📍 [Геолокация]({maps_link})"
    elif address:
        full_description += f"\n📍 Адрес: {address}"

    async with db.session() as conn:
        request_repo = RequestRepository(conn)
        request_id = await request_repo.create({
            "user_id": user_id,
            "type": "urgent",
            "service_subtype": service_type,
            "city": city,
            "description": full_description,
            "status": "new",
            "created_at": datetime.now().isoformat()
        })

        sent_msg = await message.answer(
            f"✅ Ваша заявка №{request_id} на услугу «{SERVICE_NAMES[service_type]}» принята.\n\n{full_description}\n\n⏳ Ожидайте предложений от специалистов.",
            parse_mode='Markdown'
        )

        await request_repo.update(request_id, {
            "client_chat_id": sent_msg.chat.id,
            "client_message_id": sent_msg.message_id
        })

        request_text = f"🆘 Новая заявка #{request_id} на {SERVICE_NAMES[service_type]}\nГород: {city}\n{description}"
        await notify_regional_admin(message.bot, city, request_text)

        # Уведомляем специалистов
        provider_repo = ServiceProviderRepository(conn)
        providers = await provider_repo.get_by_city_and_type(city, service_type)
        for provider in providers:
            try:
                await message.bot.send_message(
                    provider.admin_id,
                    f"🆘 Новая заявка #{request_id} на услугу «{SERVICE_NAMES[service_type]}»\n"
                    f"Город: {city}\n"
                    f"{full_description}\n\n"
                    "Предложите цену:",
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="💰 Предложить цену", callback_data=f"urgent_offer_{request_id}")]
                    ])
                )
            except Exception as e:
                logger.error(f"Не удалось уведомить специалиста {provider.admin_id}: {e}")

    await state.clear()


# ========== Специалисты: предложение цены ==========
@router.callback_query(F.data.startswith("urgent_offer_"))
async def urgent_offer_price(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    request_id = int(callback.data.split("_")[2])

    async with db.session() as conn:
        provider_repo = ServiceProviderRepository(conn)
        provider = await provider_repo.get_by_admin_id(user_id)
        if not provider:
            await callback.answer("Вы не зарегистрированы как специалист.", show_alert=True)
            return

        # Проверяем, что услуга совпадает
        request_repo = RequestRepository(conn)
        req = await request_repo.get_by_id(request_id)
        if not req or req.service_subtype != provider.service_type:
            await callback.answer("Эта заявка не соответствует вашему профилю.", show_alert=True)
            return

    await state.update_data(request_id=request_id, provider_id=provider.id)
    await state.set_state(UrgentServicesStates.entering_price)
    await callback.message.answer("Введите вашу цену (в KZT):")
    await callback.answer()


@router.message(StateFilter(UrgentServicesStates.entering_price))
async def urgent_price_entered(message: Message, state: FSMContext):
    try:
        price = int(message.text)
    except ValueError:
        await message.answer("Введите число.")
        return

    data = await state.get_data()
    request_id = data['request_id']
    provider_id = data['provider_id']

    async with db.session() as conn:
        await conn.execute(
            "INSERT INTO service_offers (request_id, provider_id, price, created_at) VALUES (?, ?, ?, ?)",
            (request_id, provider_id, price, datetime.now().isoformat())
        )
        await conn.commit()

    await update_urgent_offers_message(message.bot, request_id)
    await message.answer("✅ Ваше предложение отправлено клиенту.")
    await state.clear()


# ========== Клиент: выбор предложения ==========
@router.callback_query(F.data.startswith("choose_urgent_off_"))
async def choose_urgent_offer(callback: CallbackQuery, state: FSMContext):
    offer_id = int(callback.data.split("_")[3])

    async with db.session() as conn:
        row = await conn.execute("""
            SELECT o.request_id, o.price, sp.name, sp.phone, r.user_id, r.client_chat_id, r.client_message_id,
                   sp.admin_id, u.full_name, u.phone
            FROM service_offers o
            JOIN service_providers sp ON o.provider_id = sp.id
            JOIN requests r ON o.request_id = r.id
            JOIN users u ON r.user_id = u.telegram_id
            WHERE o.id = ?
        """, (offer_id,))
        offer = await row.fetchone()
        if not offer:
            await callback.answer("Предложение не найдено")
            return

        request_id, price, sp_name, sp_phone, client_id, chat_id, msg_id, sp_admin_id, client_name, client_phone = offer

        # Отмечаем выбранное предложение
        await conn.execute("UPDATE service_offers SET is_selected = 1 WHERE id = ?", (offer_id,))
        await conn.execute("UPDATE requests SET status = 'accepted', accepted_by = ? WHERE id = ?", (offer_id, request_id))
        await conn.commit()

    # Сообщение клиенту
    await callback.message.edit_text(
        f"✅ Вы выбрали предложение от {sp_name} на сумму {price} KZT.\n\n"
        f"📞 Телефон для связи: {sp_phone}\n"
        "Свяжитесь с исполнителем."
    )

    # Клавиатура для специалиста для обновления статуса
    status_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚗 В пути", callback_data=f"urgent_status_{request_id}_in_progress")],
        [InlineKeyboardButton(text="📍 На месте", callback_data=f"urgent_status_{request_id}_on_site")],
        [InlineKeyboardButton(text="✅ Выполнено", callback_data=f"urgent_status_{request_id}_completed")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"urgent_status_{request_id}_cancelled")]
    ])

    # Уведомляем специалиста
    await callback.bot.send_message(
        sp_admin_id,
        f"✅ Ваше предложение по заявке #{request_id} выбрано клиентом!\n\n"
        f"💰 Сумма: {price} KZT\n"
        f"Контакты клиента:\nИмя: {client_name or 'не указано'}\n📞 Телефон: {client_phone or 'не указан'}\n\n"
        "Управляйте статусом:",
        reply_markup=status_kb
    )
    await callback.answer()


# ========== Специалист: обновление статуса ==========
@router.callback_query(F.data.startswith("urgent_status_"))
async def urgent_status_update(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    request_id = int(parts[2])
    new_status = parts[3]

    # Преобразование коротких кодов
    short_map = {'in': 'in_progress', 'on': 'on_site', 'done': 'completed', 'cancel': 'cancelled'}
    if new_status in short_map:
        new_status = short_map[new_status]

    user_id = callback.from_user.id
    async with db.session() as conn:
        # Проверяем, что специалист является владельцем заявки
        row = await conn.execute("""
            SELECT sp.admin_id, r.user_id, r.status, r.city
            FROM requests r
            JOIN service_offers o ON r.id = o.request_id
            JOIN service_providers sp ON o.provider_id = sp.id
            WHERE r.id = ? AND sp.admin_id = ? AND o.is_selected = 1
        """, (request_id, user_id))
        req = await row.fetchone()
        if not req:
            await callback.answer("Заявка не найдена или не ваша.", show_alert=True)
            return
        admin_id, client_id, current_status, city = req

        await conn.execute("UPDATE requests SET status = ? WHERE id = ?", (new_status, request_id))
        await conn.commit()

    # Уведомляем клиента
    client_messages = {
        'in_progress': '🚗 Специалист выехал к вам!',
        'on_site': '📍 Специалист на месте.',
        'completed': '✅ Заявка выполнена! Оцените работу.',
        'cancelled': '❌ Заявка отменена исполнителем.'
    }
    client_text = client_messages.get(new_status, f"Статус заявки #{request_id} изменён.")
    await callback.bot.send_message(client_id, client_text)

    if new_status == 'completed':
        rate_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=str(i), callback_data=f"rate_urgent_{request_id}_{i}") for i in range(1,6)]
        ])
        await callback.bot.send_message(
            client_id,
            "Благодарим! Оцените работу от 1 до 5:",
            reply_markup=rate_kb
        )
        # FIX: уведомление регионального админа
        if city:
            await notify_regional_admin(callback.bot, city, f"Срочная заявка #{request_id} выполнена")

    # Обновляем сообщение у специалиста
    new_text = callback.message.text + f"\n\n✅ Статус обновлён: {new_status}"
    if new_status in ('completed', 'cancelled'):
        await callback.message.edit_text(new_text, reply_markup=None)
    else:
        await callback.message.edit_text(new_text, reply_markup=callback.message.reply_markup)

    await callback.answer()


# ========== Оценка работы ==========
@router.callback_query(F.data.startswith("rate_urgent_"))
async def process_rate_urgent(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    if len(parts) != 4:
        await callback.answer("Ошибка данных")
        return
    request_id = int(parts[2])
    rating = int(parts[3])

    async with db.session() as conn:
        # Находим исполнителя (provider_id) через service_offers
        row = await conn.execute("""
            SELECT o.provider_id
            FROM service_offers o
            WHERE o.request_id = ? AND o.is_selected = 1
        """, (request_id,))
        offer = await row.fetchone()
        if not offer:
            await callback.answer("Ошибка: исполнитель не определён.", show_alert=True)
            return
        provider_id = offer[0]

        # Сохраняем отзыв
        cursor = await conn.execute(
            "INSERT INTO reviews (user_id, entity_type, entity_id, rating, comment, moderated, hidden) VALUES (?, 'service_provider', ?, ?, '', 0, 0)",
            (callback.from_user.id, provider_id, rating)
        )
        review_id = cursor.lastrowid
        await conn.commit()

    await state.update_data(review_id=review_id)
    await state.set_state(ClientStates.waiting_for_review_text)

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"Спасибо за оценку {rating}⭐! Теперь вы можете оставить текстовый отзыв (или отправьте /пропустить)."
    )
    await callback.answer()


# ========== Специалист: просмотр своих заявок ==========
@router.message(F.text == "📋 Мои заявки")
async def service_provider_requests(message: Message):
    user_id = message.from_user.id
    async with db.session() as conn:
        provider_repo = ServiceProviderRepository(conn)
        provider = await provider_repo.get_by_admin_id(user_id)
        if not provider:
            await message.answer("Вы не зарегистрированы как специалист.")
            return

        rows = await conn.execute("""
            SELECT r.id, r.description, r.created_at, r.status
            FROM requests r
            WHERE r.type = 'urgent' AND r.service_subtype = ?
            ORDER BY r.created_at DESC
            LIMIT 50
        """, (provider.service_type,))
        requests = await rows.fetchall()

    if not requests:
        await message.answer("Нет заявок по вашему профилю.")
        return

    for req in requests:
        req_id, desc, created, status = req
        status_emoji = {
            'new': '🆕',
            'accepted': '✅',
            'in_progress': '🚗',
            'completed': '✔️',
            'cancelled': '❌'
        }.get(status, '📌')
        short_desc = desc[:50] + "..." if len(desc) > 50 else desc
        date_str = created[:10] if created else ""
        text = f"{status_emoji} #{req_id} от {date_str}\n{short_desc}"

        buttons = []
        if status == 'new':
            buttons.append(InlineKeyboardButton(text="💰 Предложить цену", callback_data=f"urgent_offer_{req_id}"))
        if buttons:
            kb = InlineKeyboardMarkup(inline_keyboard=[buttons])
            await message.answer(text, reply_markup=kb)
        else:
            await message.answer(text)