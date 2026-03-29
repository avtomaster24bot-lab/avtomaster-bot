# handlers/part_tender.py
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from database import db
from utils.helpers import notify_supplier_cancelled, notify_supplier_chosen, notify_other_suppliers_closed

router = Router()

@router.callback_query(F.data.startswith("cancel_part_req:"))
async def cancel_part_request(callback: CallbackQuery, state: FSMContext):
    request_id = int(callback.data.split(":")[1])
    async with db.session() as conn:
        cursor = await conn.execute("SELECT * FROM part_requests WHERE id = ?", (request_id,))
        request = await cursor.fetchone()
        if not request or request[5] not in ('new', 'active'):
            await callback.answer("Заявка уже неактивна", show_alert=True)
            return
        await conn.execute("UPDATE part_requests SET status = 'cancelled' WHERE id = ?", (request_id,))
        await conn.commit()
        cursor = await conn.execute("SELECT supplier_id FROM part_offers WHERE request_id = ?", (request_id,))
        offers = await cursor.fetchall()
    for (supplier_id,) in offers:
        await notify_supplier_cancelled(callback.bot, supplier_id, request_id)
    await callback.message.edit_text(
        callback.message.text + "\n\n❌ Заявка отменена вами.",
        reply_markup=None
    )
    await callback.answer("Заявка отменена")
    await state.clear()

@router.callback_query(F.data.startswith("choose_part_offer:"))
async def choose_part_offer(callback: CallbackQuery, state: FSMContext):
    offer_id = int(callback.data.split(":")[1])
    async with db.session() as conn:
        cursor = await conn.execute(
            """SELECT po.request_id, po.price, po.supplier_id, po.id,
                      pr.status, pr.client_chat_id, pr.client_message_id,
                      u_client.telegram_id as client_tg_id, u_client.full_name as client_name, u_client.phone as client_phone,
                      u_supp.telegram_id as supplier_tg_id, u_supp.full_name as supplier_name, u_supp.phone as supplier_phone
               FROM part_offers po
               JOIN part_requests pr ON po.request_id = pr.id
               JOIN users u_client ON pr.user_id = u_client.telegram_id
               JOIN suppliers s ON po.supplier_id = s.id
               JOIN users u_supp ON s.admin_id = u_supp.telegram_id
               WHERE po.id = ?""",
            (offer_id,)
        )
        offer = await cursor.fetchone()
        if not offer:
            await callback.answer("Предложение не найдено", show_alert=True)
            return

        (request_id, price, supplier_id, offer_id,
         status, client_chat_id, client_message_id,
         client_tg_id, client_name, client_phone,
         supplier_tg_id, supplier_name, supplier_phone) = offer

        if status not in ('new', 'active'):
            await callback.answer("Эта заявка уже закрыта", show_alert=True)
            return

        await conn.execute("UPDATE part_offers SET is_selected = 1 WHERE id = ?", (offer_id,))
        await conn.execute("UPDATE part_requests SET status = 'completed', accepted_by = ? WHERE id = ?", (supplier_id, request_id))
        
        # Исправление: получаем telegram_id других поставщиков
        cursor = await conn.execute("""
            SELECT u.telegram_id FROM part_offers po
            JOIN suppliers s ON po.supplier_id = s.id
            JOIN users u ON s.admin_id = u.telegram_id
            WHERE po.request_id = ? AND po.id != ?
        """, (request_id, offer_id))
        other_offers_rows = await cursor.fetchall()
        other_supplier_ids = [row[0] for row in other_offers_rows]  # теперь это telegram_id
        await conn.commit()

    client_text = (
        f"✅ Вы выбрали предложение от {supplier_name} на сумму {price} ₸.\n\n"
        f"Контакты поставщика:\n"
        f"📞 Телефон: {supplier_phone or 'не указан'}\n"
        f"📱 Telegram: id {supplier_tg_id} (пользователь)\n\n"
        f"Свяжитесь с ним для уточнения деталей."
    )
    await callback.message.edit_text(client_text, reply_markup=None)

    await notify_supplier_chosen(
        bot=callback.bot,
        supplier_tg_id=supplier_tg_id,
        request_id=request_id,
        client_name=client_name,
        client_phone=client_phone,
        client_username=callback.from_user.username or "",
        price=price
    )

    await notify_other_suppliers_closed(callback.bot, other_supplier_ids, request_id)

    await callback.answer("Вы выбрали предложение")
    await state.clear()