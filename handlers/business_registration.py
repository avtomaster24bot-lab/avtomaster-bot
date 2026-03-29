# handlers/business_registration.py
import json
from datetime import datetime
from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from keyboards.reply import main_menu_kb, back_kb
from keyboards.inline import (
    partner_type_kb, supplier_type_kb, yes_no_kb,
    confirm_request_kb, review_partner_request_kb, urgent_service_type_kb
)
from states.client_states import ClientStates
from database import db
from utils.helpers import notify_regional_admin, get_city_id, generate_wash_slots
import aiosqlite   # <-- добавить импорт aiosqlite

router = Router()

@router.message(F.text == "💼 Для бизнеса")
async def business_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    async with db.session() as conn:
        cursor = await conn.execute("SELECT city, role FROM users WHERE telegram_id = ?", (user_id,))
        user = await cursor.fetchone()
        if not user or not user[0]:
            await message.answer("Сначала выберите город в /start")
            return
        if user[1] != 'client':
            await message.answer("Вы уже зарегистрированы как партнёр. Для добавления новой организации обратитесь к администратору.")
            return
        city = user[0]
    await state.update_data(city=city)
    await state.set_state(ClientStates.choosing_partner_type)
    await message.answer(
        "Выберите тип бизнеса, который хотите зарегистрировать:",
        reply_markup=partner_type_kb()
    )

@router.callback_query(StateFilter(ClientStates.choosing_partner_type), F.data.startswith("partner_type:"))
async def partner_type_chosen(callback: CallbackQuery, state: FSMContext):
    partner_type = callback.data.split(":")[1]
    if partner_type == 'urgent':
        await state.update_data(partner_type='urgent')
        await state.set_state(ClientStates.choosing_urgent_service_type)
        await callback.message.edit_text(
            "Выберите тип срочной услуги:",
            reply_markup=urgent_service_type_kb()
        )
    else:
        await state.update_data(partner_type=partner_type)
        await state.set_state(ClientStates.entering_partner_name)
        await callback.message.edit_text(
            "Введите название вашей организации (например, «Автосервис на Гагарина» или «СТО Мастер»):"
        )
    await callback.answer()

@router.callback_query(StateFilter(ClientStates.choosing_urgent_service_type), F.data.startswith("urgent_type:"))
async def urgent_type_chosen(callback: CallbackQuery, state: FSMContext):
    service_type = callback.data.split(":")[1]
    await state.update_data(service_subtype=service_type)
    await state.set_state(ClientStates.entering_partner_name)
    await callback.message.edit_text(
        "Введите название вашей организации или имя (например, «Иван Петров, вскрытие замков»):"
    )
    await callback.answer()

@router.callback_query(F.data == "partner:cancel")
async def partner_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Регистрация отменена.")
    await callback.message.answer("Главное меню:", reply_markup=main_menu_kb('client'))
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "partner:back")
async def partner_back(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ClientStates.choosing_partner_type)
    await callback.message.edit_text(
        "Выберите тип бизнеса:",
        reply_markup=partner_type_kb()
    )
    await callback.answer()

@router.message(StateFilter(ClientStates.entering_partner_name))
async def partner_name_entered(message: Message, state: FSMContext):
    name = message.text
    await state.update_data(name=name)
    await state.set_state(ClientStates.entering_partner_address)
    await message.answer("Введите адрес организации (например, ул. Абая, 15):", reply_markup=back_kb())

@router.message(StateFilter(ClientStates.entering_partner_address))
async def partner_address_entered(message: Message, state: FSMContext):
    address = message.text
    await state.update_data(address=address)
    await state.set_state(ClientStates.entering_partner_phone)
    await message.answer("Введите контактный телефон (например, +7 777 123 45 67):", reply_markup=back_kb())

@router.message(StateFilter(ClientStates.entering_partner_phone))
async def partner_phone_entered(message: Message, state: FSMContext):
    phone = message.text
    await state.update_data(phone=phone)
    await state.set_state(ClientStates.entering_partner_work_hours)
    await message.answer(
        "Введите режим работы (например, пн-пт 09:00–20:00, сб 10:00–18:00).\n"
        "Если не хотите указывать, отправьте /пропустить:",
        reply_markup=back_kb()
    )

@router.message(StateFilter(ClientStates.entering_partner_work_hours))
async def partner_work_hours_entered(message: Message, state: FSMContext):
    work_hours = message.text if message.text != "/пропустить" else ""
    await state.update_data(work_hours=work_hours)
    data = await state.get_data()
    partner_type = data['partner_type']

    if partner_type == 'sto':
        await state.set_state(ClientStates.choosing_partner_categories)
        await show_category_choice(message, state)
    elif partner_type == 'wash':
        await state.set_state(ClientStates.entering_partner_boxes)
        await message.answer("Введите количество боксов (число):")
    elif partner_type == 'tow':
        await show_confirmation(message, state)
    elif partner_type == 'supplier':
        await state.set_state(ClientStates.choosing_supplier_type)
        await message.answer("Выберите тип поставщика:", reply_markup=supplier_type_kb())
    elif partner_type == 'urgent':
        await show_confirmation(message, state)

async def show_category_choice(message: Message, state: FSMContext):
    data = await state.get_data()
    city = data['city']
    async with db.session() as conn:
        cursor = await conn.execute('''
            SELECT c.id, c.name FROM categories c
            JOIN cities ct ON c.city_id = ct.id
            WHERE ct.name = ?
        ''', (city,))
        categories = await cursor.fetchall()
    if not categories:
        await state.update_data(categories=[])
        await show_confirmation(message, state)
        return
    text = "Выберите категории услуг, которые вы предоставляете (можно несколько, через запятую):\n"
    for cat_id, cat_name in categories:
        text += f"{cat_id}. {cat_name}\n"
    text += "\nНапишите номера категорий через запятую или /пропустить."
    await message.answer(text)

@router.message(StateFilter(ClientStates.choosing_partner_categories))
async def partner_categories_chosen(message: Message, state: FSMContext):
    text = message.text
    selected = []
    if text != "/пропустить":
        parts = text.split(',')
        for p in parts:
            if p.strip().isdigit():
                selected.append(int(p.strip()))
    await state.update_data(categories=selected)
    await show_confirmation(message, state)

@router.message(StateFilter(ClientStates.entering_partner_boxes))
async def partner_boxes_entered(message: Message, state: FSMContext):
    try:
        boxes = int(message.text)
    except ValueError:
        await message.answer("Введите число.")
        return
    await state.update_data(boxes=boxes)
    await state.set_state(ClientStates.entering_partner_duration)
    await message.answer("Введите среднюю длительность мойки (в минутах):")

@router.message(StateFilter(ClientStates.entering_partner_duration))
async def partner_duration_entered(message: Message, state: FSMContext):
    try:
        duration = int(message.text)
    except ValueError:
        await message.answer("Введите число.")
        return
    await state.update_data(duration=duration)
    await show_confirmation(message, state)

@router.callback_query(StateFilter(ClientStates.choosing_supplier_type), F.data.startswith("supplier_type:"))
async def supplier_type_chosen(callback: CallbackQuery, state: FSMContext):
    supplier_type = callback.data.split(":")[1]
    await state.update_data(supplier_type=supplier_type)
    await state.set_state(ClientStates.asking_delivery)
    await callback.message.edit_text(
        "Есть ли доставка?",
        reply_markup=yes_no_kb("delivery")
    )
    await callback.answer()

@router.callback_query(StateFilter(ClientStates.asking_delivery), F.data.startswith("delivery:"))
async def delivery_chosen(callback: CallbackQuery, state: FSMContext):
    delivery = callback.data.split(":")[1] == "yes"
    await state.update_data(delivery_available=delivery)
    await show_confirmation(callback.message, state)
    await callback.message.delete()
    await callback.answer()

async def show_confirmation(message: Message, state: FSMContext):
    data = await state.get_data()
    text = "📋 Проверьте введённые данные:\n\n"
    text += f"📌 Тип: {data['partner_type']}\n"
    text += f"🏢 Название: {data['name']}\n"
    text += f"📍 Адрес: {data['address']}\n"
    text += f"📞 Телефон: {data['phone']}\n"
    if data.get('work_hours'):
        text += f"🕒 Режим работы: {data['work_hours']}\n"
    if data.get('categories'):
        async with db.session() as conn:
            placeholders = ','.join('?' for _ in data['categories'])
            cursor = await conn.execute(f"SELECT name FROM categories WHERE id IN ({placeholders})", data['categories'])
            cats = await cursor.fetchall()
            cat_names = [c[0] for c in cats]
            text += f"🔧 Категории: {', '.join(cat_names)}\n"
    if data.get('boxes'):
        text += f"🚿 Боксов: {data['boxes']}\n"
        text += f"⏱ Длительность мойки: {data['duration']} мин\n"
    if data.get('supplier_type'):
        type_map = {'shop': 'Магазин', 'dismantler': 'Разборка', 'installer': 'Установщик'}
        text += f"📦 Тип поставщика: {type_map[data['supplier_type']]}\n"
    if 'delivery_available' in data:
        text += f"🚚 Доставка: {'Да' if data['delivery_available'] else 'Нет'}\n"
    if data.get('service_subtype'):
        service_names = {
            'locksmith': '🔓 Вскрытие замков',
            'tire': '🛞 Выездной шиномонтаж',
            'delivery': '📦 Доставка запчастей',
            'electrician': '⚡ Автоэлектрик',
            'mechanic': '🔧 Мастер-универсал'
        }
        text += f"🆘 Тип срочной услуги: {service_names.get(data['service_subtype'], data['service_subtype'])}\n"
    text += "\nВсё верно? Отправьте заявку."

    await state.set_state(ClientStates.confirming_partner_request)
    if isinstance(message, Message):
        await message.answer(text, reply_markup=confirm_request_kb())
    else:
        await message.answer(text, reply_markup=confirm_request_kb())

@router.callback_query(StateFilter(ClientStates.confirming_partner_request), F.data == "partner:confirm")
async def partner_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = callback.from_user.id
    city = data['city']
    partner_type = data['partner_type']
    name = data['name']
    address = data['address']
    phone = data['phone']
    work_hours = data.get('work_hours', '')
    categories = json.dumps(data.get('categories', []))
    boxes = data.get('boxes')
    duration = data.get('duration')
    supplier_type = data.get('supplier_type', '')
    delivery = data.get('delivery_available')
    service_subtype = data.get('service_subtype')

    async with db.session() as conn:
        cursor = await conn.execute('''
            INSERT INTO partner_requests
            (user_id, city, partner_type, name, address, phone, work_hours, categories, boxes, duration, supplier_type, delivery_available, service_subtype, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, city, partner_type, name, address, phone, work_hours, categories, boxes, duration, supplier_type, delivery, service_subtype, 'pending', datetime.now().isoformat()))
        request_id = cursor.lastrowid
        await conn.commit()

    request_text = (
        f"📋 Новая заявка на партнёрство #{request_id}\n"
        f"Тип: {partner_type}\n"
        f"Организация: {name}\n"
        f"Город: {city}\n"
        f"Телефон: {phone}"
    )
    await notify_regional_admin(callback.bot, city, request_text, extra_markup=review_partner_request_kb(request_id))

    await callback.message.edit_text(
        "✅ Заявка отправлена! Региональный администратор рассмотрит её в ближайшее время. Вы получите уведомление о решении."
    )
    await callback.message.answer("Главное меню:", reply_markup=main_menu_kb('client'))
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "partner:restart")
async def partner_restart(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await business_start(callback.message, state)
    await callback.message.delete()
    await callback.answer()

# Обработчики для регионального админа (одобрение/отклонение)
@router.callback_query(F.data.startswith("approve_partner:"))
async def approve_partner(callback: CallbackQuery, state: FSMContext):
    request_id = int(callback.data.split(":")[1])
    admin_id = callback.from_user.id

    async with db.session() as conn:
        conn.row_factory = aiosqlite.Row   # FIX: правильный объект соединения
        cursor = await conn.execute("SELECT * FROM partner_requests WHERE id = ?", (request_id,))
        request = await cursor.fetchone()
        if not request or request['status'] != 'pending':
            await callback.answer("Заявка уже обработана.", show_alert=True)
            return

        user_id = request['user_id']
        partner_type = request['partner_type']
        city = request['city']
        name = request['name']
        address = request['address']
        phone = request['phone']
        work_hours = request['work_hours']
        categories = json.loads(request['categories']) if request['categories'] else []
        boxes = request['boxes']
        duration = request['duration']
        supplier_type = request['supplier_type']
        delivery = request['delivery_available']
        service_subtype = request['service_subtype']

        await conn.execute(
            "UPDATE partner_requests SET status = 'approved', reviewed_at = ?, reviewed_by = ? WHERE id = ?",
            (datetime.now().isoformat(), admin_id, request_id)
        )

        city_id = await get_city_id(city)

        if partner_type == 'sto':
            cursor = await conn.execute('''
                INSERT INTO stations (name, city_id, admin_id, phone, address, work_hours)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (name, city_id, user_id, phone, address, work_hours))
            station_id = cursor.lastrowid
            for cat_id in categories:
                await conn.execute('''
                    INSERT INTO station_categories (station_id, category_id) VALUES (?, ?)
                ''', (station_id, cat_id))
            await conn.execute("UPDATE users SET role = 'station_admin' WHERE telegram_id = ?", (user_id,))

        elif partner_type == 'wash':
            cursor = await conn.execute('''
                INSERT INTO car_washes (name, city_id, admin_id, phone, address, working_hours, boxes, duration)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (name, city_id, user_id, phone, address, work_hours, boxes, duration))
            wash_id = cursor.lastrowid
            await conn.execute("UPDATE users SET role = 'wash_admin' WHERE telegram_id = ?", (user_id,))
            await generate_wash_slots(wash_id, days=7)

        elif partner_type == 'tow':
            await conn.execute('''
                INSERT INTO tow_trucks (name, city_id, admin_id, phone, address)
                VALUES (?, ?, ?, ?, ?)
            ''', (name, city_id, user_id, phone, address))
            await conn.execute("UPDATE users SET role = 'tow_admin' WHERE telegram_id = ?", (user_id,))

        elif partner_type == 'supplier':
            await conn.execute('''
                INSERT INTO suppliers (name, type, city_id, admin_id, phone, address, work_hours, delivery_available)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (name, supplier_type, city_id, user_id, phone, address, work_hours, delivery))
            await conn.execute("UPDATE users SET role = 'supplier' WHERE telegram_id = ?", (user_id,))

        elif partner_type == 'urgent':
            await conn.execute('''
                INSERT INTO service_providers (service_type, name, city_id, admin_id, phone, address, rating, reviews_count, subscription_until)
                VALUES (?, ?, ?, ?, ?, ?, 0, 0, NULL)
            ''', (service_subtype, name, city_id, user_id, phone, address))
            await conn.execute("UPDATE users SET role = 'service_provider' WHERE telegram_id = ?", (user_id,))

        await conn.commit()

    # Отправляем уведомление пользователю
    if partner_type == 'wash':
        message_text = f"🎉 Ура! Ваша заявка на регистрацию «{name}» одобрена!\n\nТеперь вы — часть большого сообщества AvtoMaster24.\n\n🚀 Чтобы начать принимать заказы, просто нажмите /start. После этого в главном меню появится раздел «🚿 Управление мойкой».\n\n⚠️ Важно: После настройки расписания не забудьте нажать кнопку «🔄 Сгенерировать слоты».\n\n🔗 Ваша персональная ссылка уже ждёт вас – поделитесь ею с клиентами!\n\nДобро пожаловать!"
    else:
        message_text = f"🎉 Ура! Ваша заявка на регистрацию «{name}» одобрена!\n\nТеперь вы — часть большого сообщества AvtoMaster24.\n\n🚀 Чтобы начать принимать заказы, просто нажмите /start.\n\n🔗 Ваша персональная ссылка уже ждёт вас – поделитесь ею с клиентами!\n\nДобро пожаловать!"

    await callback.bot.send_message(user_id, message_text, parse_mode='Markdown')
    await callback.message.edit_text(
        callback.message.text + "\n\n✅ Заявка одобрена. Пользователь уведомлён."
    )
    await callback.answer("Заявка одобрена")

@router.callback_query(F.data.startswith("reject_partner:"))
async def reject_partner(callback: CallbackQuery, state: FSMContext):
    request_id = int(callback.data.split(":")[1])
    admin_id = callback.from_user.id

    async with db.session() as conn:
        cursor = await conn.execute("SELECT user_id FROM partner_requests WHERE id = ?", (request_id,))
        row = await cursor.fetchone()
        if not row:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        user_id = row[0]
        await conn.execute(
            "UPDATE partner_requests SET status = 'rejected', reviewed_at = ?, reviewed_by = ? WHERE id = ?",
            (datetime.now().isoformat(), admin_id, request_id)
        )
        await conn.commit()

    await callback.bot.send_message(
        user_id,
        f"❌ К сожалению, ваша заявка на партнёрство отклонена. Обратитесь к администратору для уточнения причин."
    )
    await callback.message.edit_text(
        callback.message.text + "\n\n❌ Заявка отклонена. Пользователь уведомлён."
    )
    await callback.answer("Заявка отклонена")