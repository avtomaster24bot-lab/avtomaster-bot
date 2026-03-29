# handlers/supplier_admin.py
import logging
from datetime import datetime
from aiogram import Router, F, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from repositories.supplier_repo import SupplierRepository
from repositories.part_request_repo import PartRequestRepository
from states.admin_states import SupplierAdminStates
from utils.helpers import update_part_offers_message, get_user_role

logger = logging.getLogger(__name__)
router = Router()


async def is_supplier(user_id: int) -> bool:
    async with db.session() as conn:
        repo = SupplierRepository(conn)
        supplier = await repo.get_by_admin_id(user_id)
        return supplier is not None


# ---------- Просмотр новых заявок (тендер) ----------
@router.message(F.text == "📦 Мои заявки на запчасти")
async def supplier_requests(message: Message, state: FSMContext):
    if not await is_supplier(message.from_user.id):
        await message.answer("Нет доступа.")
        return

    user_id = message.from_user.id
    async with db.session() as conn:
        supplier_repo = SupplierRepository(conn)
        supplier = await supplier_repo.get_by_admin_id(user_id)
        if not supplier:
            await message.answer("Вы не зарегистрированы как поставщик.")
            return
        supplier_id = supplier.id
        # Получаем город поставщика
        cursor = await conn.execute("SELECT city FROM users WHERE telegram_id = ?", (user_id,))
        city_row = await cursor.fetchone()
        city = city_row[0] if city_row else None
        if not city:
            await message.answer("Ваш город не определён.")
            return

        # Заявки, которые ещё новые и на которые этот поставщик ещё не предлагал цену
        part_req_repo = PartRequestRepository(conn)
        rows = await part_req_repo._fetch_all("""
            SELECT pr.id, pr.part_name, pr.car_info, pr.comment, pr.created_at
            FROM part_requests pr
            WHERE pr.city = ? AND pr.status = 'new'
              AND NOT EXISTS (
                  SELECT 1 FROM part_offers po
                  WHERE po.request_id = pr.id AND po.supplier_id = ?
              )
            ORDER BY pr.created_at ASC
        """, (city, supplier_id))

        if not rows:
            await message.answer("Новых заявок нет.")
            return

        for req in rows:
            req_id, part_name, car_info, comment, created = req
            text = (
                f"📢 Заявка #{req_id}\n"
                f"Деталь: {part_name}\n"
                f"Авто: {car_info if car_info else 'не указано'}\n"
                f"Комментарий: {comment if comment else 'нет'}\n"
                f"Создана: {created[:16] if created else 'неизвестно'}"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💰 Предложить цену", callback_data=f"supplier_offer_{req_id}")]
            ])
            await message.answer(text, reply_markup=kb)


# ---------- Предложение цены ----------
@router.callback_query(F.data.startswith("supplier_offer_"))
async def supplier_offer_price(callback: CallbackQuery, state: FSMContext):
    if not await is_supplier(callback.from_user.id):
        await callback.answer("Нет прав")
        return
    request_id = int(callback.data.split("_")[2])
    await state.update_data(request_id=request_id)
    await state.set_state(SupplierAdminStates.entering_price)
    await callback.message.answer("Введите вашу цену (в KZT):")
    await callback.answer()


@router.message(StateFilter(SupplierAdminStates.entering_price))
async def supplier_price_entered(message: Message, state: FSMContext):
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
            await message.answer("Вы не зарегистрированы как поставщик.")
            await state.clear()
            return
        supplier_id = supplier.id

        # Сохраняем предложение
        await conn.execute(
            "INSERT INTO part_offers (request_id, supplier_id, price, comment, created_at) VALUES (?, ?, ?, ?, ?)",
            (request_id, supplier_id, price, "", datetime.now().isoformat())
        )
        await conn.commit()

    # Обновляем сообщение клиента, добавляя новое предложение
    await update_part_offers_message(message.bot, request_id)

    await message.answer("✅ Ваше предложение отправлено клиенту.")
    await state.clear()


# ---------- Просмотр своих предложений ----------
@router.message(F.text == "💰 Мои предложения")
async def my_offers(message: Message):
    if not await is_supplier(message.from_user.id):
        return

    user_id = message.from_user.id
    async with db.session() as conn:
        supplier_repo = SupplierRepository(conn)
        supplier = await supplier_repo.get_by_admin_id(user_id)
        if not supplier:
            await message.answer("Вы не зарегистрированы.")
            return
        supplier_id = supplier.id

        rows = await conn.execute("""
            SELECT po.id, pr.part_name, po.price, po.created_at, pr.status
            FROM part_offers po
            JOIN part_requests pr ON po.request_id = pr.id
            WHERE po.supplier_id = ?
            ORDER BY po.created_at ASC
        """, (supplier_id,))
        offers = await rows.fetchall()

    if not offers:
        await message.answer("У вас пока нет предложений.")
        return

    text = "📄 Ваши предложения:\n\n"
    for off_id, part_name, price, created, status in offers:
        date_str = created[:16] if created else ""
        text += f"#{off_id} – {part_name}, {price} KZT, статус заявки: {status}\n"
    await message.answer(text)