# handlers/tow_admin.py
import logging
from datetime import datetime
from aiogram import Router, F, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from repositories.tow_truck_repo import TowTruckRepository
from repositories.request_repo import RequestRepository
from states.admin_states import TowAdminStates
from states.client_states import ClientStates
from utils.helpers import update_tow_offers_message, stars_from_rating, notify_regional_admin  # добавлен notify_regional_admin

logger = logging.getLogger(__name__)
router = Router()


async def is_tow_admin(user_id: int) -> bool:
    async with db.session() as conn:
        repo = TowTruckRepository(conn)
        truck = await repo.get_by_admin_id(user_id)
        return truck is not None


# ---------- Просмотр активных заявок ----------
@router.message(F.text == "🚨 Мои заявки")
async def tow_panel(message: Message, state: FSMContext):
    if not await is_tow_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return

    user_id = message.from_user.id
    async with db.session() as conn:
        truck_repo = TowTruckRepository(conn)
        truck = await truck_repo.get_by_admin_id(user_id)
        if not truck:
            await message.answer("Вы не привязаны к эвакуатору.")
            return
        truck_id = truck.id

        request_repo = RequestRepository(conn)
        rows = await request_repo._fetch_all(
            """SELECT r.id, r.description, r.created_at, r.status, r.user_id
               FROM requests r
               LEFT JOIN tow_offers o ON r.id = o.request_id AND o.tower_id = ?
               WHERE r.type = 'tow' AND (r.status IN ('accepted', 'in_progress', 'on_site')
                   OR (r.status = 'new' AND o.id IS NULL))
               ORDER BY r.created_at DESC""",
            (truck_id,)
        )
        if not rows:
            await message.answer("Нет активных заявок.")
            return

        text = "Ваши активные заявки:\n\n"
        for req_id, desc, created, status, client_id in rows:
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


# ---------- Предложение цены (из новой заявки) ----------
@router.callback_query(F.data.startswith("tow_offer_"))
async def offer_price(callback: CallbackQuery, state: FSMContext):
    if not await is_tow_admin(callback.from_user.id):
        await callback.answer("Нет прав")
        return

    request_id = int(callback.data.split("_")[2])
    await state.update_data(request_id=request_id)
    await state.set_state(TowAdminStates.entering_price)
    await callback.message.answer("Введите вашу цену (в KZT):")
    await callback.answer()


@router.message(StateFilter(TowAdminStates.entering_price))
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
        truck_repo = TowTruckRepository(conn)
        truck = await truck_repo.get_by_admin_id(user_id)
        if not truck:
            await message.answer("Вы не привязаны к эвакуатору.")
            await state.clear()
            return
        truck_id = truck.id

        cursor = await conn.execute(
            "SELECT status, type FROM requests WHERE id = ?",
            (request_id,)
        )
        req_row = await cursor.fetchone()
        if not req_row or req_row[1] != "tow" or req_row[0] != "new":
            await message.answer("Эта заявка уже закрыта/принята или не относится к эвакуатору.")
            await state.clear()
            return

        await conn.execute(
            "INSERT INTO tow_offers (request_id, tower_id, price, created_at) VALUES (?, ?, ?, ?)",
            (request_id, truck_id, price, datetime.now().isoformat())
        )
        await conn.commit()

# 🔥 ВАЖНО — отправка клиенту
cursor = await conn.execute(
    "SELECT user_id FROM requests WHERE id = ?",
    (request_id,)
)
row = await cursor.fetchone()

if row and row[0]:
    client_id = row[0]

    await message.bot.send_message(
        chat_id=client_id,
        text=f"🚗 Новое предложение по вашей заявке #{request_id}\n\n💰 Цена: {price} тг"
    )

await update_tow_offers_message(message.bot, request_id)

await message.answer("✅ Ваше предложение отправлено клиенту.")

    await update_tow_offers_message(message.bot, request_id)

    await message.answer("✅ Ваше предложение отправлено клиенту.")
    await state.clear()


# ---------- Обновление статуса заявки (для принятых) ----------
@router.message(F.text == "📌 Обновить статус")
async def update_status_prompt(message: Message, state: FSMContext):
    if not await is_tow_admin(message.from_user.id):
        return
    await state.set_state(TowAdminStates.entering_tow_request_id)
    await message.answer("Введите номер заявки:")


@router.message(StateFilter(TowAdminStates.entering_tow_request_id))
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
        if req.type != 'tow':
            await message.answer("Это не заявка на эвакуатор.")
            return
        truck_repo = TowTruckRepository(conn)
        truck = await truck_repo.get_by_admin_id(user_id)
        if not truck or req.accepted_by != truck.id:
            await message.answer("Заявка не принадлежит вашему эвакуатору.")
            return
        current_status = req.status

    await state.update_data(request_id=req_id, current_status=current_status)
    await state.set_state(TowAdminStates.choosing_tow_status)

    kb = types.ReplyKeyboardMarkup(keyboard=[
        [types.KeyboardButton(text="🚗 В пути")],
        [types.KeyboardButton(text="📍 На месте")],
        [types.KeyboardButton(text="✅ Выполнено")],
        [types.KeyboardButton(text="❌ Отмена")]
    ], resize_keyboard=True)

    await message.answer(f"Текущий статус: {current_status}\nВыберите новый:", reply_markup=kb)


@router.message(StateFilter(TowAdminStates.choosing_tow_status))
async def set_tow_status(message: Message, state: FSMContext):
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
                client_text = f"🚗 Эвакуатор выехал к вам (заявка #{req_id})."
            elif new_status == 'on_site':
                client_text = f"📍 Эвакуатор на месте (заявка #{req_id})."
            elif new_status == 'completed':
                client_text = (
                    f"✅ Заявка #{req_id} выполнена!\n"
                    "Пожалуйста, оцените работу эвакуатора от 1 до 5:"
                )
                rate_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=str(i), callback_data=f"rate_tow_{req_id}_{i}") for i in range(1,6)]
                ])
                await message.bot.send_message(req.user_id, client_text, reply_markup=rate_kb)
                await message.answer("Статус изменён на «Выполнено». Клиент получил уведомление с кнопкой оценки.")
                # Уведомление регионального админа
                if req.city:
                    await notify_regional_admin(message.bot, req.city, f"Заявка на эвакуатор #{req_id} выполнена")
                await state.clear()
                return
            elif new_status == 'cancelled':
                client_text = f"❌ Заявка #{req_id} отменена эвакуатором."
            else:
                client_text = f"Статус заявки #{req_id} изменён: {message.text}."
            await message.bot.send_message(req.user_id, client_text)

    await message.answer(f"Статус заявки #{req_id} изменён на {message.text}.", reply_markup=types.ReplyKeyboardRemove())
    await state.clear()


# ---------- Обработка callback статуса из карточки клиента ----------
@router.callback_query(F.data.startswith("tow_status_"))
async def tow_status_callback(callback: CallbackQuery, state: FSMContext):
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
        truck_repo = TowTruckRepository(conn)
        truck = await truck_repo.get_by_admin_id(user_id)
        if not truck:
            await callback.answer("Вы не привязаны к эвакуатору.", show_alert=True)
            return
        request_repo = RequestRepository(conn)
        req = await request_repo.get_by_id(request_id)
        if not req or req.accepted_by != truck.id:
            await callback.answer("Заявка не принадлежит вам.", show_alert=True)
            return

        await request_repo.update(request_id, {"status": new_status})
        if new_status == 'completed':
            await request_repo.update(request_id, {"completed_at": datetime.now().isoformat()})
        await conn.commit()

        if req.user_id:
            if new_status == 'in_progress':
                text = f"🚗 Эвакуатор выехал к вам (заявка #{request_id})."
            elif new_status == 'on_site':
                text = f"📍 Эвакуатор на месте (заявка #{request_id})."
            elif new_status == 'completed':
                text = (
                    f"✅ Заявка #{request_id} выполнена!\n"
                    "Пожалуйста, оцените работу эвакуатора от 1 до 5:"
                )
                rate_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=str(i), callback_data=f"rate_tow_{request_id}_{i}") for i in range(1,6)]
                ])
                await callback.bot.send_message(req.user_id, text, reply_markup=rate_kb)
                # Уведомление регионального админа
                if req.city:
                    await notify_regional_admin(callback.bot, req.city, f"Заявка на эвакуатор #{request_id} выполнена")
            elif new_status == 'cancelled':
                text = f"❌ Заявка #{request_id} отменена эвакуатором."
                await callback.bot.send_message(req.user_id, text)
            else:
                text = f"Статус заявки #{request_id} изменён на {new_status}."
                await callback.bot.send_message(req.user_id, text)

    if new_status in ('completed', 'cancelled'):
        await callback.message.edit_text(callback.message.text + "\n\n✅ Заявка закрыта.")
    else:
        await callback.message.edit_text(callback.message.text + f"\n\n✅ Статус обновлён: {new_status}")

    await callback.answer("Статус обновлён")


# ========== ОБРАБОТЧИК ОЦЕНКИ ЭВАКУАТОРА ==========
@router.callback_query(F.data.startswith("rate_tow_"))
async def process_rate_tow(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    if len(parts) != 4:
        await callback.answer("Ошибка данных")
        return
    request_id = int(parts[2])
    rating = int(parts[3])

    async with db.session() as conn:
        # Находим tow_id по accepted_by в заявке
        cursor = await conn.execute("SELECT accepted_by FROM requests WHERE id = ?", (request_id,))
        row = await cursor.fetchone()
        if not row or not row[0]:
            await callback.answer("Ошибка: эвакуатор не определён.", show_alert=True)
            return
        tow_id = row[0]

        # Сохраняем отзыв
        cursor = await conn.execute(
            "INSERT INTO reviews (user_id, entity_type, entity_id, rating, comment, moderated, hidden) VALUES (?, 'tow_truck', ?, ?, '', 0, 0)",
            (callback.from_user.id, tow_id, rating)
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