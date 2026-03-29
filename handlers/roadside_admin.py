# handlers/roadside_admin.py
import logging
from datetime import datetime
from aiogram import Router, F, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from repositories.supplier_repo import SupplierRepository
from repositories.request_repo import RequestRepository
from states.admin_states import RoadsideAdminStates
from states.client_states import ClientStates
from utils.helpers import update_roadside_offers_message, get_user_role, notify_regional_admin  # FIX: добавлен notify_regional_admin

logger = logging.getLogger(__name__)
router = Router()


async def is_roadside_admin(user_id: int) -> bool:
    async with db.session() as conn:
        repo = SupplierRepository(conn)
        supplier = await repo.get_by_admin_id(user_id)
        return supplier is not None


# ---------- Просмотр активных заявок ----------
@router.message(F.text == "🆘 Мои заявки")
async def roadside_panel(message: Message, state: FSMContext):
    if not await is_roadside_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return

    user_id = message.from_user.id
    async with db.session() as conn:
        supplier_repo = SupplierRepository(conn)
        supplier = await supplier_repo.get_by_admin_id(user_id)
        if not supplier:
            await message.answer("Вы не зарегистрированы как специалист автопомощи.")
            return
        supplier_id = supplier.id

        rows = await conn.execute("""
            SELECT r.id, r.description, r.created_at, r.status, r.user_id
            FROM requests r
            LEFT JOIN roadside_offers o ON r.id = o.request_id AND o.specialist_id = ?
            WHERE r.type = 'roadside' 
              AND (r.status IN ('accepted', 'in_progress', 'on_site') 
                   OR (r.status = 'new' AND o.id IS NULL))
            ORDER BY r.created_at DESC
        """, (supplier_id,))
        requests = await rows.fetchall()

    if not requests:
        await message.answer("Нет активных заявок.")
        return

    text = "Ваши активные заявки:\n\n"
    for req_id, desc, created, status, client_id in requests:
        status_emoji = {
            'new': '🆕',
            'accepted': '✅',
            'in_progress': '🚗',
            'on_site': '📍',
            'completed': '✔️',
            'cancelled': '❌'
        }.get(status, '📌')
        date_str = created[:10] if created else ""
        short_desc = (desc[:50] + '...') if len(desc) > 50 else desc
        text += f"{status_emoji} #{req_id} от {date_str}\n{short_desc}\n\n"

    await message.answer(text)


# ---------- Предложение цены ----------
@router.callback_query(F.data.startswith("roadside_offer_"))
async def offer_price(callback: CallbackQuery, state: FSMContext):
    if not await is_roadside_admin(callback.from_user.id):
        await callback.answer("Нет прав")
        return
    request_id = int(callback.data.split("_")[2])
    await state.update_data(request_id=request_id)
    await state.set_state(RoadsideAdminStates.entering_price)
    await callback.message.answer("Введите вашу цену (в KZT):")
    await callback.answer()


@router.message(StateFilter(RoadsideAdminStates.entering_price))
async def price_entered(message: Message, state: FSMContext):
    try:
        price = int(message.text)
    except ValueError:
        await message.answer("Введите число.")
        return

    data = await state.get_data()
    request_id = data['request_id']
    user_id = message.from_user.id

    async with db.session() as conn:
        supplier_repo = SupplierRepository(conn)
        supplier = await supplier_repo.get_by_admin_id(user_id)
        if not supplier:
            await message.answer("Вы не привязаны к профилю специалиста.")
            return
        specialist_id = supplier.id

        await conn.execute(
            "INSERT INTO roadside_offers (request_id, specialist_id, price, created_at) VALUES (?, ?, ?, ?)",
            (request_id, specialist_id, price, datetime.now().isoformat())
        )
        await conn.commit()

    await update_roadside_offers_message(message.bot, request_id)

    await message.answer("✅ Ваше предложение отправлено клиенту.")
    await state.clear()


# ---------- Обновление статуса (для принятых заявок) ----------
@router.message(F.text == "📌 Обновить статус")
async def update_status_prompt(message: Message, state: FSMContext):
    if not await is_roadside_admin(message.from_user.id):
        return
    await state.set_state(RoadsideAdminStates.entering_request_id)
    await message.answer("Введите номер заявки:")


@router.message(StateFilter(RoadsideAdminStates.entering_request_id))
async def enter_request_id(message: Message, state: FSMContext):
    try:
        req_id = int(message.text)
    except ValueError:
        await message.answer("Неверный номер.")
        return

    user_id = message.from_user.id
    async with db.session() as conn:
        request_repo = RequestRepository(conn)
        req = await request_repo.get_by_id(req_id)
        if not req:
            await message.answer("Заявка не найдена.")
            return
        if req.type != 'roadside':
            await message.answer("Это не заявка на автопомощь.")
            return
        supplier_repo = SupplierRepository(conn)
        supplier = await supplier_repo.get_by_admin_id(user_id)
        if not supplier or req.accepted_by != supplier.id:
            await message.answer("Заявка не принадлежит вашему профилю.")
            return
        current_status = req.status

    await state.update_data(request_id=req_id, current_status=current_status)
    await state.set_state(RoadsideAdminStates.choosing_status)

    kb = types.ReplyKeyboardMarkup(keyboard=[
        [types.KeyboardButton(text="🚗 В пути")],
        [types.KeyboardButton(text="📍 На месте")],
        [types.KeyboardButton(text="✅ Выполнено")],
        [types.KeyboardButton(text="❌ Отмена")]
    ], resize_keyboard=True)
    await message.answer(f"Текущий статус: {current_status}\nВыберите новый:", reply_markup=kb)


@router.message(StateFilter(RoadsideAdminStates.choosing_status))
async def set_status(message: Message, state: FSMContext):
    status_map = {
        "🚗 В пути": "in_progress",
        "📍 На месте": "on_site",
        "✅ Выполнено": "completed",
        "❌ Отмена": "cancelled"
    }
    if message.text not in status_map:
        await message.answer("Неверный выбор.")
        return
    new_status = status_map[message.text]

    data = await state.get_data()
    req_id = data['request_id']

    async with db.session() as conn:
        request_repo = RequestRepository(conn)
        await request_repo.update(req_id, {"status": new_status})
        if new_status == 'completed':
            await request_repo.update(req_id, {"completed_at": datetime.now().isoformat()})
        await conn.commit()

        req = await request_repo.get_by_id(req_id)
        if req and req.user_id:
            if new_status == 'in_progress':
                client_text = f"🚗 Специалист выехал к вам (заявка #{req_id})."
            elif new_status == 'on_site':
                client_text = f"📍 Специалист на месте (заявка #{req_id})."
            elif new_status == 'completed':
                client_text = (
                    f"✅ Заявка #{req_id} выполнена!\n"
                    "Пожалуйста, оцените работу специалиста от 1 до 5:"
                )
                rate_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=str(i), callback_data=f"rate_roadside_{req_id}_{i}") for i in range(1,6)]
                ])
                await message.bot.send_message(req.user_id, client_text, reply_markup=rate_kb)
                await message.answer("Статус изменён на «Выполнено». Клиент получил кнопку оценки.")
                # FIX: уведомление регионального админа
                if req.city:
                    await notify_regional_admin(message.bot, req.city, f"Заявка на автопомощь #{req_id} выполнена")
                await state.clear()
                return
            elif new_status == 'cancelled':
                client_text = f"❌ Заявка #{req_id} отменена специалистом."
            else:
                client_text = f"Статус заявки #{req_id} изменён на {message.text}."
            await message.bot.send_message(req.user_id, client_text)

    await message.answer(f"Статус заявки #{req_id} изменён на {message.text}.", reply_markup=types.ReplyKeyboardRemove())
    await state.clear()


# ---------- Обработка callback статуса из карточки клиента ----------
@router.callback_query(F.data.startswith("roadside_status_"))
async def roadside_status_callback(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer("Неверный формат")
        return
    request_id = int(parts[2])
    new_status = parts[3]

    short_map = {'in': 'in_progress', 'on': 'on_site', 'done': 'completed', 'cancel': 'cancelled'}
    if new_status in short_map:
        new_status = short_map[new_status]

    user_id = callback.from_user.id
    async with db.session() as conn:
        supplier_repo = SupplierRepository(conn)
        supplier = await supplier_repo.get_by_admin_id(user_id)
        if not supplier:
            await callback.answer("Вы не привязаны к профилю специалиста.", show_alert=True)
            return
        request_repo = RequestRepository(conn)
        req = await request_repo.get_by_id(request_id)
        if not req or req.accepted_by != supplier.id:
            await callback.answer("Заявка не принадлежит вам.", show_alert=True)
            return

        await request_repo.update(request_id, {"status": new_status})
        if new_status == 'completed':
            await request_repo.update(request_id, {"completed_at": datetime.now().isoformat()})
        await conn.commit()

        if req.user_id:
            if new_status == 'in_progress':
                text = f"🚗 Специалист выехал к вам (заявка #{request_id})."
            elif new_status == 'on_site':
                text = f"📍 Специалист на месте (заявка #{request_id})."
            elif new_status == 'completed':
                text = (
                    f"✅ Заявка #{request_id} выполнена!\n"
                    "Пожалуйста, оцените работу специалиста от 1 до 5:"
                )
                rate_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=str(i), callback_data=f"rate_roadside_{request_id}_{i}") for i in range(1,6)]
                ])
                await callback.bot.send_message(req.user_id, text, reply_markup=rate_kb)
                # FIX: уведомление регионального админа
                if req.city:
                    await notify_regional_admin(callback.bot, req.city, f"Заявка на автопомощь #{request_id} выполнена")
            elif new_status == 'cancelled':
                text = f"❌ Заявка #{request_id} отменена специалистом."
                await callback.bot.send_message(req.user_id, text)
            else:
                text = f"Статус заявки #{request_id} изменён на {new_status}."
                await callback.bot.send_message(req.user_id, text)

    if new_status in ('completed', 'cancelled'):
        await callback.message.edit_text(callback.message.text + "\n\n✅ Заявка закрыта.")
    else:
        await callback.message.edit_text(callback.message.text + f"\n\n✅ Статус обновлён: {new_status}")

    await callback.answer("Статус обновлён")


# ========== ОБРАБОТЧИК ОЦЕНКИ АВТОПОМОЩИ ==========
@router.callback_query(F.data.startswith("rate_roadside_"))
async def process_rate_roadside(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    if len(parts) != 4:
        await callback.answer("Ошибка данных")
        return
    request_id = int(parts[2])
    rating = int(parts[3])

    async with db.session() as conn:
        # Находим specialist_id по accepted_by
        cursor = await conn.execute("SELECT accepted_by FROM requests WHERE id = ?", (request_id,))
        row = await cursor.fetchone()
        if not row or not row[0]:
            await callback.answer("Ошибка: специалист не определён.", show_alert=True)
            return
        specialist_id = row[0]

        # Сохраняем отзыв
        cursor = await conn.execute(
            "INSERT INTO reviews (user_id, entity_type, entity_id, rating, comment, moderated, hidden) VALUES (?, 'supplier', ?, ?, '', 0, 0)",
            (callback.from_user.id, specialist_id, rating)
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