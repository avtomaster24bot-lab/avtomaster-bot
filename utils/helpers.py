# utils/helpers.py
import aiosqlite
import logging
import json
from datetime import datetime, timedelta
from math import radians, sin, cos, sqrt, asin
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db

# IMPROVEMENT: добавлен логгер
logger = logging.getLogger(__name__)

# ========== Основные функции ==========

async def get_user_role(telegram_id):
    """Возвращает роль пользователя по telegram_id."""
    async with db.session() as conn:
        cursor = await conn.execute("SELECT role FROM users WHERE telegram_id = ?", (telegram_id,))
        row = await cursor.fetchone()
        return row[0] if row else None

async def set_user_role(telegram_id, role):
    """Устанавливает роль пользователя."""
    async with db.session() as conn:
        await conn.execute("UPDATE users SET role = ? WHERE telegram_id = ?", (role, telegram_id))
        await conn.commit()

async def get_city_name(city_id):
    """Возвращает название города по его ID."""
    async with db.session() as conn:
        cursor = await conn.execute("SELECT name FROM cities WHERE id = ?", (city_id,))
        row = await cursor.fetchone()
        return row[0] if row else None

async def get_city_id(city_name):
    """Возвращает ID города по названию."""
    async with db.session() as conn:
        cursor = await conn.execute("SELECT id FROM cities WHERE name = ?", (city_name,))
        row = await cursor.fetchone()
        return row[0] if row else None

async def get_user_city(user_id: int) -> str | None:
    """Возвращает город пользователя по его telegram_id."""
    async with db.session() as conn:
        cursor = await conn.execute("SELECT city FROM users WHERE telegram_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else None

async def notify_regional_admin(bot, city, request_text, extra_markup=None):
    """Отправляет уведомление региональному администратору города."""
    async with db.session() as conn:
        cursor = await conn.execute(
            "SELECT telegram_id FROM users WHERE role = 'regional_admin' AND city = ?",
            (city,)
        )
        regional = await cursor.fetchone()
        if regional:
            try:
                await bot.send_message(regional[0], f"📢 Новая заявка в вашем городе {city}:\n{request_text}",
                                       reply_markup=extra_markup)
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление региональному админу {regional[0]}: {e}")

async def notify_regional_admin_about_review(bot, entity_type, entity_id, rating, comment=""):
    """Отправляет уведомление региональным администраторам города о новом отзыве."""
    async with db.session() as conn:
        # Определяем город и название объекта
        city_name = None
        obj_name = None
        if entity_type in ('station', 'sto'):
            cursor = await conn.execute("SELECT city_id, name FROM stations WHERE id = ?", (entity_id,))
            row = await cursor.fetchone()
            if row:
                city_id, obj_name = row
                cursor = await conn.execute("SELECT name FROM cities WHERE id = ?", (city_id,))
                city_row = await cursor.fetchone()
                city_name = city_row[0] if city_row else None
        elif entity_type == 'car_wash':
            cursor = await conn.execute("SELECT city_id, name FROM car_washes WHERE id = ?", (entity_id,))
            row = await cursor.fetchone()
            if row:
                city_id, obj_name = row
                cursor = await conn.execute("SELECT name FROM cities WHERE id = ?", (city_id,))
                city_row = await cursor.fetchone()
                city_name = city_row[0] if city_row else None
        elif entity_type == 'tow_truck':
            cursor = await conn.execute("SELECT city_id, name FROM tow_trucks WHERE id = ?", (entity_id,))
            row = await cursor.fetchone()
            if row:
                city_id, obj_name = row
                cursor = await conn.execute("SELECT name FROM cities WHERE id = ?", (city_id,))
                city_row = await cursor.fetchone()
                city_name = city_row[0] if city_row else None
        elif entity_type == 'supplier':
            cursor = await conn.execute("SELECT city_id, name FROM suppliers WHERE id = ?", (entity_id,))
            row = await cursor.fetchone()
            if row:
                city_id, obj_name = row
                cursor = await conn.execute("SELECT name FROM cities WHERE id = ?", (city_id,))
                city_row = await cursor.fetchone()
                city_name = city_row[0] if city_row else None
        elif entity_type == 'service_provider':
            cursor = await conn.execute("SELECT city_id, name FROM service_providers WHERE id = ?", (entity_id,))
            row = await cursor.fetchone()
            if row:
                city_id, obj_name = row
                cursor = await conn.execute("SELECT name FROM cities WHERE id = ?", (city_id,))
                city_row = await cursor.fetchone()
                city_name = city_row[0] if city_row else None
        else:
            return

        if not city_name or not obj_name:
            return

        text = f"⭐ Новый отзыв для {obj_name}\nОценка: {rating}⭐"
        if comment:
            text += f"\n📝 Комментарий: {comment}"
        text += "\nТребуется модерация."

        cursor = await conn.execute("SELECT telegram_id FROM users WHERE role = 'regional_admin' AND city = ?", (city_name,))
        admins = await cursor.fetchall()
        for (admin_id,) in admins:
            try:
                await bot.send_message(admin_id, text)
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление админу {admin_id}: {e}")

async def notify_client_about_part_offer(bot, offer_id):
    """Уведомляет клиента о новом предложении по его заявке на запчасть."""
    async with db.session() as conn:
        cursor = await conn.execute('''
            SELECT pr.user_id, pr.part_name, po.price
            FROM part_offers po
            JOIN part_requests pr ON po.request_id = pr.id
            WHERE po.id = ?
        ''', (offer_id,))
        row = await cursor.fetchone()
        if not row:
            return
        user_id, part_name, price = row
        try:
            await bot.send_message(
                user_id,
                f"📦 По вашему запросу «{part_name}» поступило новое предложение: {price} KZT.\n"
                f"Посмотреть его можно в сообщении с вашим запросом."
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление клиенту {user_id}: {e}")

async def notify_supplier_cancelled(bot, supplier_id, request_id):
    """Уведомляет поставщика об отмене его предложения."""
    try:
        await bot.send_message(
            supplier_id,
            f"❌ Ваше предложение по заявке #{request_id} отклонено (клиент выбрал другого поставщика или отменил заявку)."
        )
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление поставщику {supplier_id}: {e}")

async def notify_supplier_chosen(bot, supplier_tg_id, request_id, client_name, client_phone, client_username, price):
    """Уведомляет поставщика о выборе его предложения (с ценой)."""
    text = (
        f"✅ Ваше предложение по заявке #{request_id} выбрано клиентом!\n\n"
        f"💰 Сумма: {price} KZT\n"
        f"Контакты клиента:\n"
        f"Имя: {client_name or 'не указано'}\n"
        f"📞 Телефон: {client_phone or 'не указан'}\n"
        f"📱 Telegram: @{client_username or 'не указан'}"
    )
    try:
        await bot.send_message(supplier_tg_id, text)
    except Exception as e:
        logger.error(f"Не удалось уведомить поставщика {supplier_tg_id}: {e}")

async def notify_other_suppliers_closed(bot, supplier_ids, request_id):
    """Уведомляет всех остальных поставщиков, что заявка закрыта."""
    for sid in supplier_ids:
        try:
            await bot.send_message(
                sid,
                f"❌ Заявка #{request_id} закрыта (клиент выбрал другого поставщика)."
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление поставщику {sid}: {e}")

def haversine(lat1, lon1, lat2, lon2):
    """
    Вычисляет расстояние между двумя точками на сфере (в км).
    Использует формулу гаверсинуса.
    """
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    r = 6371
    return c * r

def stars_from_rating(rating: float) -> str:
    """
    Преобразует числовой рейтинг (0-5) в строку из звёздочек и половинок.

    Args:
        rating: Числовой рейтинг.

    Returns:
        str: Строка вида "⭐⭐⭐⯨☆".
    """
    if rating is None:
        return "☆☆☆☆☆"
    full = int(rating)
    fraction = rating - full
    if fraction >= 0.75:
        full += 1
        half = False
    elif fraction >= 0.25:
        half = True
    else:
        half = False
    stars = "⭐" * full
    if half:
        stars += "⯨"  # половинка
    stars += "☆" * (5 - full - (1 if half else 0))
    return stars

# ========== Функции обновления сообщений с предложениями ==========

async def update_tow_offers_message(bot, request_id):
    """Обновляет сообщение клиента со списком предложений эвакуаторов."""
    async with db.session() as conn:
        cursor = await conn.execute('''
            SELECT client_chat_id, client_message_id, description, city, status
            FROM requests WHERE id = ? AND type = 'tow'
        ''', (request_id,))
        req = await cursor.fetchone()
        if not req:
            return
        chat_id, msg_id, description, city, status = req

        cursor = await conn.execute('''
            SELECT o.id, o.price, t.name, t.id, t.rating
            FROM tow_offers o
            JOIN tow_trucks t ON o.tower_id = t.id
            WHERE o.request_id = ? AND (o.is_selected IS NULL OR o.is_selected = 0)
            ORDER BY o.created_at
        ''', (request_id,))
        offers = await cursor.fetchall()

    text = f"🚨 Ваша заявка на эвакуатор №{request_id}\n\n"
    text += description + "\n\n"
    if status == 'accepted':
        text += "✅ Заявка принята, ожидайте.\n"
    if offers:
        text += "📋 Поступившие предложения:\n"
        for idx, (offer_id, price, name, tower_id, rating) in enumerate(offers, 1):
            stars = stars_from_rating(rating or 0)
            text += f"{idx}. {name} {stars} – {price} KZT\n"

        buttons = []
        for offer_id, price, name, tower_id, rating in offers:
            buttons.append([
                InlineKeyboardButton(text="✅ Выбрать", callback_data=f"choose_tow_off_{offer_id}"),
                InlineKeyboardButton(text="⭐ Отзывы", callback_data=f"view_reviews_tow_{tower_id}")
            ])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    else:
        text += "Пока нет предложений. Ожидайте."
        kb = None

    try:
        if kb:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, reply_markup=kb)
        else:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id)
    except Exception as e:
        logger.warning(f"Не удалось обновить сообщение заявки {request_id}: {e}")

async def update_roadside_offers_message(bot, request_id):
    """Обновляет сообщение клиента со списком предложений по автопомощи."""
    async with db.session() as conn:
        cursor = await conn.execute('''
            SELECT client_chat_id, client_message_id, description, city, status
            FROM requests WHERE id = ? AND type = 'roadside'
        ''', (request_id,))
        req = await cursor.fetchone()
        if not req:
            return
        chat_id, msg_id, description, city, status = req

        cursor = await conn.execute('''
            SELECT o.id, o.price, s.name, s.id
            FROM roadside_offers o
            JOIN suppliers s ON o.specialist_id = s.id
            WHERE o.request_id = ? AND (o.is_selected IS NULL OR o.is_selected = 0)
            ORDER BY o.created_at
        ''', (request_id,))
        offers = await cursor.fetchall()

    text = f"🆘 Ваша заявка на автопомощь №{request_id}\n\n"
    text += description + "\n\n"
    if status == 'accepted':
        text += "✅ Заявка принята, ожидайте.\n"
    if offers:
        text += "📋 Поступившие предложения:\n"
        for idx, (offer_id, price, name, provider_id) in enumerate(offers, 1):
            text += f"{idx}. {name} – {price} KZT\n"

        buttons = []
        for offer_id, price, name, provider_id in offers:
            buttons.append([
                InlineKeyboardButton(text="✅ Выбрать", callback_data=f"choose_roadside_off_{offer_id}"),
                InlineKeyboardButton(text="⭐ Отзывы", callback_data=f"view_reviews_service_provider_{provider_id}")
            ])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    else:
        text += "⏳ Пока нет предложений. Ожидайте."
        kb = None

    try:
        if kb:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, reply_markup=kb)
        else:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id)
    except Exception as e:
        logger.warning(f"Не удалось обновить сообщение заявки {request_id}: {e}")

async def update_part_offers_message(bot, request_id):
    """Обновляет сообщение клиента с запросом запчасти, добавляя список предложений и кнопки выбора."""
    async with db.session() as conn:
        # FIX: исправлен статус с 'active' на 'new'
        cursor = await conn.execute('''
            SELECT client_chat_id, client_message_id, part_name, car_info, comment, city, status
            FROM part_requests WHERE id = ? AND status = 'new'
        ''', (request_id,))
        req = await cursor.fetchone()
        if not req:
            return
        chat_id, msg_id, part_name, car_info, comment, city, status = req

        cursor = await conn.execute('''
            SELECT o.id, o.price, s.name, s.id
            FROM part_offers o
            JOIN suppliers s ON o.supplier_id = s.id
            WHERE o.request_id = ? AND (o.is_selected IS NULL OR o.is_selected = 0)
            ORDER BY o.created_at
        ''', (request_id,))
        offers = await cursor.fetchall()

    text = (f"📦 Ваш запрос на запчасть №{request_id}\n\n"
            f"🔧 Деталь: {part_name}\n"
            f"🚗 Авто: {car_info if car_info else 'не указано'}\n"
            f"📝 Комментарий: {comment if comment else 'нет'}\n\n")
    if status == 'completed':
        text += "✅ Заявка закрыта, выбран поставщик.\n"
    elif offers:
        text += "📋 Поступившие предложения:\n"
        for idx, (offer_id, price, supplier_name, supplier_db_id) in enumerate(offers, 1):
            text += f"{idx}. {supplier_name} – {price} KZT\n"
        buttons = []
        for offer_id, price, supplier_name, supplier_db_id in offers:
            buttons.append([
                InlineKeyboardButton(text="✅ Выбрать", callback_data=f"choose_part_offer:{offer_id}"),
                InlineKeyboardButton(text="⭐ Отзывы", callback_data=f"view_reviews_supplier_{supplier_db_id}")
            ])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    else:
        text += "Пока нет предложений. Ожидайте."
        kb = None

    try:
        if kb:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, reply_markup=kb)
        else:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id)
    except Exception as e:
        logger.warning(f"Не удалось обновить сообщение запроса {request_id}: {e}")

async def update_urgent_offers_message(bot, request_id):
    """Обновляет сообщение клиента со списком предложений по срочным услугам."""
    async with db.session() as conn:
        cursor = await conn.execute('''
            SELECT client_chat_id, client_message_id, description, city, status, service_subtype
            FROM requests WHERE id = ? AND type = 'urgent'
        ''', (request_id,))
        req = await cursor.fetchone()
        if not req:
            return
        chat_id, msg_id, description, city, status, service_type = req

        cursor = await conn.execute('''
            SELECT o.id, o.price, sp.name, sp.id
            FROM service_offers o
            JOIN service_providers sp ON o.provider_id = sp.id
            WHERE o.request_id = ? AND (o.is_selected IS NULL OR o.is_selected = 0)
            ORDER BY o.created_at
        ''', (request_id,))
        offers = await cursor.fetchall()

    service_names = {
        'locksmith': '🔓 Вскрытие замков',
        'tire': '🛞 Выездной шиномонтаж',
        'delivery': '📦 Доставка запчастей',
        'electrician': '⚡ Автоэлектрик',
        'mechanic': '🔧 Мастер-универсал'
    }
    service_name = service_names.get(service_type, service_type)
    text = f"🆘 Ваша заявка на {service_name} №{request_id}\n\n"
    text += description + "\n\n"
    if status == 'accepted':
        text += "✅ Заявка принята, ожидайте.\n"
    if offers:
        text += "📋 Поступившие предложения:\n"
        buttons = []
        for i, (offer_id, price, name, provider_id) in enumerate(offers, 1):
            text += f"{i}. {name} – {price} KZT\n"
            buttons.append([
                InlineKeyboardButton(text=f"✅ Выбрать {i}", callback_data=f"choose_urgent_off_{offer_id}"),
                InlineKeyboardButton(text="⭐ Отзывы", callback_data=f"view_reviews_service_provider_{provider_id}")
            ])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    else:
        text += "Пока нет предложений. Ожидайте."
        kb = None

    try:
        if kb:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, reply_markup=kb)
        else:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id)
    except Exception as e:
        logger.warning(f"Не удалось обновить сообщение заявки {request_id}: {e}")

async def update_offers_message(bot, request_id, request_type):
    """Универсальная обёртка для вызова update_*_offers_message по типу заявки."""
    if request_type == 'tow':
        await update_tow_offers_message(bot, request_id)
    elif request_type == 'urgent':
        await update_urgent_offers_message(bot, request_id)
    elif request_type == 'roadside':
        await update_roadside_offers_message(bot, request_id)
    else:
        logger.warning(f"Неизвестный тип заявки для обновления: {request_type}")

# ========== Функция генерации слотов для моек ==========

async def generate_wash_slots(
    wash_id: int,
    start_date=None,
    days: int = 7,
    slot_duration: int = None,
    break_duration: int = None,
    work_start: str = None,
    work_end: str = None,
    days_off: list = None
) -> int:
    """
    Генерирует слоты для мойки на указанное количество дней.

    Если параметры не переданы, берёт их из БД.

    Args:
        wash_id: ID мойки.
        start_date: Дата начала (datetime.date). Если None, используется текущая дата.
        days: Количество дней, на которые генерировать слоты (по умолчанию 7).
        slot_duration: Длительность слота в минутах.
        break_duration: Длительность перерыва между слотами в минутах.
        work_start: Время начала работы (формат "HH:MM").
        work_end: Время окончания работы (формат "HH:MM").
        days_off: Список выходных дней (названия дней недели: "ПН", "ВТ", ...).

    Returns:
        int: Количество созданных слотов.
    """
    if start_date is None:
        start_date = datetime.now().date()
    if start_date < datetime.now().date():
        start_date = datetime.now().date()

    async with db.session() as conn:
        if any(v is None for v in [slot_duration, break_duration, work_start, work_end, days_off]):
            cursor = await conn.execute(
                "SELECT boxes, slot_duration, break_duration, work_start, work_end, days_off FROM car_washes WHERE id = ?",
                (wash_id,)
            )
            row = await cursor.fetchone()
            if not row:
                logger.error(f"Мойка {wash_id} не найдена")
                return 0
            boxes, slot_dur, break_dur, w_start, w_end, days_off_json = row
            if slot_duration is None:
                slot_duration = slot_dur
            if break_duration is None:
                break_duration = break_dur
            if work_start is None:
                work_start = w_start
            if work_end is None:
                work_end = w_end
            if days_off is None and days_off_json:
                days_off = json.loads(days_off_json)
            else:
                days_off = days_off or []
        else:
            cursor = await conn.execute("SELECT boxes FROM car_washes WHERE id = ?", (wash_id,))
            row = await cursor.fetchone()
            boxes = row[0] if row else 1

    try:
        start_h, start_m = map(int, work_start.split(':'))
        end_h, end_m = map(int, work_end.split(':'))
    except Exception as e:
        logger.error(f"Неверный формат времени работы: {e}")
        return 0

    day_map = {
        'ПН': 0, 'ВТ': 1, 'СР': 2, 'ЧТ': 3, 'ПТ': 4, 'СБ': 5, 'ВС': 6,
        'пн': 0, 'вт': 1, 'ср': 2, 'чт': 3, 'пт': 4, 'сб': 5, 'вс': 6
    }
    off_days = set()
    for d in days_off:
        d_clean = d.strip().upper()[:2]
        if d_clean in day_map:
            off_days.add(day_map[d_clean])

    count = 0
    async with db.session() as conn:
        for day_offset in range(days):
            current_date = start_date + timedelta(days=day_offset)
            if current_date.weekday() in off_days:
                continue

            for box in range(1, boxes + 1):
                slot_start = datetime(
                    current_date.year, current_date.month, current_date.day,
                    start_h, start_m
                )
                day_end = datetime(
                    current_date.year, current_date.month, current_date.day,
                    end_h, end_m
                )

                while slot_start + timedelta(minutes=slot_duration) <= day_end:
                    slot_datetime = slot_start.strftime('%Y-%m-%d %H:%M:%S')
                    await conn.execute('''
                        INSERT OR IGNORE INTO wash_slots (wash_id, datetime, status)
                        VALUES (?, ?, 'free')
                    ''', (wash_id, slot_datetime))
                    count += 1
                    slot_start += timedelta(minutes=slot_duration + break_duration)

        await conn.commit()
        logger.info(f"Сгенерировано {count} слотов для мойки {wash_id}")
        return count