# handlers/wash_admin.py
import json
import logging
from datetime import datetime, timedelta
from aiogram import Router, F, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

from database import db
from repositories.car_wash_repo import CarWashRepository
from states.admin_states import WashAdminStates
from states.client_states import ClientStates
from keyboards.reply import main_menu_kb, back_kb
from utils.helpers import generate_wash_slots, stars_from_rating, get_user_role

logger = logging.getLogger(__name__)
router = Router()


async def is_wash_admin(user_id: int) -> bool:
    async with db.session() as conn:
        repo = CarWashRepository(conn)
        wash = await repo.get_by_admin_id(user_id)
        return wash is not None


# ---------- Главная панель ----------
@router.message(F.text == "🚿 Управление мойкой")
async def wash_admin_panel(message: Message, state: FSMContext):
    if not await is_wash_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    kb = types.ReplyKeyboardMarkup(keyboard=[
        [types.KeyboardButton(text="📅 Мои слоты")],
        [types.KeyboardButton(text="⚙ Настройки мойки"), types.KeyboardButton(text="📊 Статистика")],
        [types.KeyboardButton(text="🔄 Сгенерировать слоты"), types.KeyboardButton(text="🔄 Управление боксами")],
        [types.KeyboardButton(text="🔗 Моя ссылка")],
        [types.KeyboardButton(text="⬅ Главное меню")]
    ], resize_keyboard=True)
    await message.answer("Панель управления мойкой:", reply_markup=kb)


# ---------- Возврат в главное меню ----------
@router.message(F.text == "⬅ Главное меню")
async def back_to_main(message: Message, state: FSMContext):
    await state.clear()
    role = await get_user_role(message.from_user.id)
    await message.answer("Главное меню:", reply_markup=main_menu_kb(role))


# ---------- Просмотр слотов ----------
@router.message(F.text == "📅 Мои слоты")
async def view_slots(message: Message, state: FSMContext):
    if not await is_wash_admin(message.from_user.id):
        return

    user_id = message.from_user.id
    async with db.session() as conn:
        wash_repo = CarWashRepository(conn)
        wash = await wash_repo.get_by_admin_id(user_id)
        if not wash:
            await message.answer("Мойка не найдена.")
            return
        wash_id = wash.id

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor = await conn.execute("""
            SELECT ws.id, ws.datetime, ws.status, ws.progress, u.telegram_id, u.full_name, u.phone
            FROM wash_slots ws
            LEFT JOIN users u ON ws.user_id = u.telegram_id
            WHERE ws.wash_id = ? AND ws.datetime >= ?
            ORDER BY ws.datetime
            LIMIT 30
        """, (wash_id, now_str))
        slots = await cursor.fetchall()

    if not slots:
        await message.answer("Нет будущих записей.")
        return

    for slot_id, dt_str, status, progress, client_id, client_name, client_phone in slots:
        if status == 'free':
            line = f"🟢 {dt_str} – свободно"
            manual_btn = InlineKeyboardButton(text="📝 Занять вручную", callback_data=f"manual_book_{slot_id}")
            kb = InlineKeyboardMarkup(inline_keyboard=[[manual_btn]])
            await message.answer(line, reply_markup=kb)
        else:
            # Занятый слот
            if client_id:
                client_info = f"Клиент: {client_phone or client_name or client_id}"
            else:
                client_info = "Ручная бронь"

            progress_map = {
                'booked': '📅 Забронировано',
                'in_progress': '🚿 Моется',
                'completed': '✅ Завершено'
            }
            progress_text = progress_map.get(progress, '📅 Забронировано')
            line = f"{'🔴' if client_id else '🟠'} {dt_str}\n{progress_text}\n{client_info}"

            buttons = []
            if progress == 'booked':
                buttons.append(InlineKeyboardButton(text="🚿 Начать мойку", callback_data=f"wash_progress_{slot_id}_in_progress"))
            elif progress == 'in_progress':
                buttons.append(InlineKeyboardButton(text="✅ Завершить", callback_data=f"wash_progress_{slot_id}_completed"))

            if progress != 'completed':
                if client_id:
                    cancel_btn = InlineKeyboardButton(text="❌ Отменить", callback_data=f"admin_cancel_wash_{slot_id}")
                else:
                    cancel_btn = InlineKeyboardButton(text="🔓 Освободить", callback_data=f"manual_free_{slot_id}")
                if buttons:
                    buttons.append(cancel_btn)
                    kb = InlineKeyboardMarkup(inline_keyboard=[buttons])
                else:
                    kb = InlineKeyboardMarkup(inline_keyboard=[[cancel_btn]])
            else:
                kb = None

            if kb:
                await message.answer(line, reply_markup=kb)
            else:
                await message.answer(line)


# ---------- Ручное занятие слота ----------
@router.callback_query(F.data.startswith("manual_book_"))
async def manual_book_slot(callback: CallbackQuery):
    if not await is_wash_admin(callback.from_user.id):
        await callback.answer("Нет прав.")
        return
    slot_id = int(callback.data.split("_")[2])
    async with db.session() as conn:
        cursor = await conn.execute("SELECT status FROM wash_slots WHERE id = ?", (slot_id,))
        row = await cursor.fetchone()
        if not row or row[0] != 'free':
            await callback.answer("Слот уже занят или не существует.", show_alert=True)
            return
        await conn.execute(
            "UPDATE wash_slots SET status = 'booked', progress = 'booked', user_id = NULL WHERE id = ?",
            (slot_id,)
        )
        await conn.commit()
    await callback.answer("Слот занят вручную.")
    await callback.message.edit_text(callback.message.text + "\n✅ Занято вручную.")
    await callback.message.edit_reply_markup(reply_markup=None)


# ---------- Ручное освобождение слота ----------
@router.callback_query(F.data.startswith("manual_free_"))
async def manual_free_slot(callback: CallbackQuery):
    if not await is_wash_admin(callback.from_user.id):
        await callback.answer("Нет прав.")
        return
    slot_id = int(callback.data.split("_")[2])
    async with db.session() as conn:
        cursor = await conn.execute("SELECT user_id FROM wash_slots WHERE id = ?", (slot_id,))
        row = await cursor.fetchone()
        if not row or row[0] is not None:
            await callback.answer("Этот слот нельзя освободить (обычная бронь).", show_alert=True)
            return
        await conn.execute(
            "UPDATE wash_slots SET status = 'free', progress = NULL, user_id = NULL WHERE id = ?",
            (slot_id,)
        )
        await conn.commit()
    await callback.answer("Слот освобождён.")
    await callback.message.edit_text(callback.message.text + "\n✅ Освобождён.")
    await callback.message.edit_reply_markup(reply_markup=None)


# ---------- Прогресс мойки ----------
@router.callback_query(F.data.startswith("wash_progress_"))
async def wash_progress_update(callback: CallbackQuery):
    if not await is_wash_admin(callback.from_user.id):
        await callback.answer("Нет прав.")
        return
    parts = callback.data.split("_", 3)
    if len(parts) < 4:
        await callback.answer("Неверный формат данных.")
        return
    slot_id = int(parts[2])
    new_progress = parts[3]

    async with db.session() as conn:
        cursor = await conn.execute("""
            SELECT ws.user_id, ws.datetime, cw.name
            FROM wash_slots ws
            JOIN car_washes cw ON ws.wash_id = cw.id
            WHERE ws.id = ?
        """, (slot_id,))
        row = await cursor.fetchone()
        if not row:
            await callback.answer("Слот не найден.", show_alert=True)
            return
        client_id, dt_str, wash_name = row

        await conn.execute(
            "UPDATE wash_slots SET progress = ? WHERE id = ?",
            (new_progress, slot_id)
        )
        await conn.commit()

        if client_id:
            if new_progress == 'in_progress':
                text = f"🚿 Мойка '{wash_name}' началась (запись на {dt_str})."
            elif new_progress == 'completed':
                text = f"✅ Мойка '{wash_name}' завершена (запись на {dt_str}). Спасибо!"
            else:
                text = f"Статус вашей записи на мойку '{wash_name}' (на {dt_str}) изменён: {new_progress}."
            await callback.bot.send_message(client_id, text)

            if new_progress == 'completed':
                rate_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=str(i), callback_data=f"rate_wash_{slot_id}_{i}") for i in range(1,6)]
                ])
                await callback.bot.send_message(client_id, "Оцените качество мойки от 1 до 5:", reply_markup=rate_kb)

    status_names = {'in_progress': '🚿 Мойка началась', 'completed': '✅ Завершено'}
    human_status = status_names.get(new_progress, new_progress)
    await callback.message.edit_text(callback.message.text + f"\n✅ Статус изменён: {human_status}.")
    await callback.answer("Статус обновлён.")


# ---------- Отмена записи администратором ----------
@router.callback_query(F.data.startswith("admin_cancel_wash_"))
async def admin_cancel_wash(callback: CallbackQuery):
    if not await is_wash_admin(callback.from_user.id):
        await callback.answer("Нет прав.")
        return
    slot_id = int(callback.data.split("_")[3])
    async with db.session() as conn:
        cursor = await conn.execute("""
            SELECT ws.user_id, ws.datetime, cw.name
            FROM wash_slots ws
            JOIN car_washes cw ON ws.wash_id = cw.id
            WHERE ws.id = ?
        """, (slot_id,))
        row = await cursor.fetchone()
        if not row or not row[0]:
            await callback.answer("Слот не найден или не занят клиентом.", show_alert=True)
            return
        client_id, dt_str, wash_name = row
        await conn.execute(
            "UPDATE wash_slots SET status = 'free', user_id = NULL, reminder_sent = 0, progress = NULL WHERE id = ?",
            (slot_id,)
        )
        await conn.commit()
        await callback.bot.send_message(
            client_id,
            f"❌ Ваша запись на мойку '{wash_name}' на {dt_str} отменена администратором."
        )
    await callback.message.edit_text(callback.message.text + "\n✅ Запись отменена администратором.")
    await callback.answer("Запись отменена.")


# ---------- Настройки мойки (FSM) ----------
@router.message(F.text == "⚙ Настройки мойки")
async def wash_settings(message: Message, state: FSMContext):
    if not await is_wash_admin(message.from_user.id):
        return

    user_id = message.from_user.id
    async with db.session() as conn:
        cursor = await conn.execute("""
            SELECT name, address, slot_duration, break_duration, work_start, work_end, days_off, boxes
            FROM car_washes WHERE admin_id = ?
        """, (user_id,))
        row = await cursor.fetchone()
    if not row:
        await message.answer("Мойка не зарегистрирована. Обратитесь к администратору.")
        return

    name, address, slot_dur, break_dur, work_start, work_end, days_off_json, boxes = row
    days_off = ", ".join(json.loads(days_off_json)) if days_off_json else "нет"

    text = (
        f"🏢 Название: {name}\n"
        f"📍 Адрес: {address}\n"
        f"🚗 Количество боксов: {boxes}\n"
        f"⏱ Длительность слота: {slot_dur} мин\n"
        f"🕐 Перерыв между слотами: {break_dur} мин\n"
        f"🕒 Рабочие часы: {work_start} - {work_end}\n"
        f"📅 Выходные: {days_off}\n\n"
        "Выберите, что хотите изменить:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Название", callback_data="edit_wash_name")],
        [InlineKeyboardButton(text="Адрес", callback_data="edit_wash_address")],
        [InlineKeyboardButton(text="Количество боксов", callback_data="edit_boxes")],
        [InlineKeyboardButton(text="Длительность слота", callback_data="edit_slot_duration")],
        [InlineKeyboardButton(text="Перерыв", callback_data="edit_break_duration")],
        [InlineKeyboardButton(text="Начало работы", callback_data="edit_work_start")],
        [InlineKeyboardButton(text="Конец работы", callback_data="edit_work_end")],
        [InlineKeyboardButton(text="Выходные дни", callback_data="edit_days_off")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="close_settings")]
    ])
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("edit_"))
async def edit_wash_field(callback: CallbackQuery, state: FSMContext):
    if not await is_wash_admin(callback.from_user.id):
        await callback.answer("Нет прав.")
        return
    field = callback.data.replace("edit_", "")
    field_map = {
        "wash_name": ("Введите новое название мойки:", WashAdminStates.name),
        "wash_address": ("Введите новый адрес:", WashAdminStates.address),
        "boxes": ("Введите количество боксов (целое число):", WashAdminStates.entering_boxes),
        "slot_duration": ("Введите длительность слота в минутах:", WashAdminStates.entering_duration),
        "break_duration": ("Введите перерыв между слотами в минутах:", WashAdminStates.entering_hours),
        "work_start": ("Введите время начала работы (ЧЧ:ММ, например 09:00):", WashAdminStates.entering_hours),
        "work_end": ("Введите время окончания работы (ЧЧ:ММ):", WashAdminStates.entering_hours),
        "days_off": ("Введите выходные дни через запятую (например: ПН, ВТ):", WashAdminStates.waiting_for_days)
    }
    if field not in field_map:
        await callback.answer("Неизвестное поле")
        return
    prompt, state_field = field_map[field]
    await state.set_state(state_field)
    await state.update_data(edit_field=field)

    await callback.message.edit_text(prompt)
    await callback.message.answer("⬅ Нажмите кнопку 'Назад', чтобы отменить изменение.", reply_markup=back_kb())
    await callback.answer()


@router.message(StateFilter(WashAdminStates))
async def process_wash_setting(message: Message, state: FSMContext):
    if message.text == "⬅ Назад":
        await back_from_settings(message, state)
        return

    if not await is_wash_admin(message.from_user.id):
        await state.clear()
        return

    current_state = await state.get_state()
    user_id = message.from_user.id
    async with db.session() as conn:
        wash = await conn.execute("SELECT id FROM car_washes WHERE admin_id = ?", (user_id,))
        wash_row = await wash.fetchone()
        if not wash_row:
            await message.answer("Мойка не найдена.")
            await state.clear()
            return
        wash_id = wash_row[0]

        # Определяем, какое поле редактируется
        data = await state.get_data()
        field = data.get('edit_field')

        if current_state == WashAdminStates.name.state or field == "wash_name":
            new_value = message.text.strip()
            await conn.execute("UPDATE car_washes SET name = ? WHERE id = ?", (new_value, wash_id))
            await message.answer("Название обновлено.", reply_markup=main_menu_kb('wash_admin'))

        elif current_state == WashAdminStates.address.state or field == "wash_address":
            new_value = message.text.strip()
            await conn.execute("UPDATE car_washes SET address = ? WHERE id = ?", (new_value, wash_id))
            await message.answer("Адрес обновлён.", reply_markup=main_menu_kb('wash_admin'))

        elif current_state == WashAdminStates.entering_boxes.state or field == "boxes":
            try:
                new_value = int(message.text)
                if new_value <= 0:
                    raise ValueError
            except ValueError:
                await message.answer("Введите положительное целое число.")
                return
            await conn.execute("UPDATE car_washes SET boxes = ? WHERE id = ?", (new_value, wash_id))
            await message.answer("Количество боксов обновлено.", reply_markup=main_menu_kb('wash_admin'))
            await ask_regenerate(message, wash_id)

        elif current_state == WashAdminStates.entering_duration.state or field == "slot_duration":
            try:
                new_value = int(message.text)
                if new_value <= 0:
                    raise ValueError
            except ValueError:
                await message.answer("Введите положительное целое число.")
                return
            await conn.execute("UPDATE car_washes SET slot_duration = ? WHERE id = ?", (new_value, wash_id))
            await message.answer("Длительность слота обновлена.", reply_markup=main_menu_kb('wash_admin'))
            await ask_regenerate(message, wash_id)

        elif current_state == WashAdminStates.entering_hours.state and field in ("break_duration", "work_start", "work_end"):
            if field == "break_duration":
                try:
                    new_value = int(message.text)
                    if new_value < 0:
                        raise ValueError
                except ValueError:
                    await message.answer("Введите целое неотрицательное число.")
                    return
                await conn.execute("UPDATE car_washes SET break_duration = ? WHERE id = ?", (new_value, wash_id))
                await message.answer("Перерыв обновлён.", reply_markup=main_menu_kb('wash_admin'))
            elif field == "work_start":
                new_value = message.text.strip()
                try:
                    datetime.strptime(new_value, "%H:%M")
                except ValueError:
                    await message.answer("Введите время в формате ЧЧ:ММ (например 09:00).")
                    return
                await conn.execute("UPDATE car_washes SET work_start = ? WHERE id = ?", (new_value, wash_id))
                await message.answer("Время начала работы обновлено.", reply_markup=main_menu_kb('wash_admin'))
            elif field == "work_end":
                new_value = message.text.strip()
                try:
                    datetime.strptime(new_value, "%H:%M")
                except ValueError:
                    await message.answer("Введите время в формате ЧЧ:ММ (например 18:00).")
                    return
                await conn.execute("UPDATE car_washes SET work_end = ? WHERE id = ?", (new_value, wash_id))
                await message.answer("Время окончания работы обновлено.", reply_markup=main_menu_kb('wash_admin'))
            await ask_regenerate(message, wash_id)

        elif current_state == WashAdminStates.waiting_for_days.state or field == "days_off":
            days = [d.strip() for d in message.text.split(",") if d.strip()]
            await conn.execute("UPDATE car_washes SET days_off = ? WHERE id = ?", (json.dumps(days), wash_id))
            await message.answer("Выходные дни обновлены.", reply_markup=main_menu_kb('wash_admin'))
            await ask_regenerate(message, wash_id)

        else:
            await message.answer("Неизвестное состояние.")
            return

    await state.clear()
    await wash_settings(message, state)  # вернуться в меню настроек


async def ask_regenerate(message: Message, wash_id: int):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Перегенерировать слоты сейчас", callback_data=f"regenerate_after_change_{wash_id}")]
    ])
    await message.answer(
        "⚠️ Чтобы изменения вступили в силу для будущих записей, необходимо перегенерировать слоты. "
        "Это удалит все будущие записи клиентов! Нажмите кнопку, если уверены.",
        reply_markup=kb
    )


@router.callback_query(F.data.startswith("regenerate_after_change_"))
async def regenerate_after_change(callback: CallbackQuery, state: FSMContext):
    wash_id = int(callback.data.split("_")[3])
    user_id = callback.from_user.id
    if not await is_wash_admin(user_id):
        await callback.answer("Нет прав.")
        return

    async with db.session() as conn:
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        await conn.execute("DELETE FROM wash_slots WHERE wash_id = ? AND datetime >= ?", (wash_id, now_str))
        await conn.commit()

        cursor = await conn.execute("""
            SELECT slot_duration, break_duration, work_start, work_end, days_off
            FROM car_washes WHERE id = ?
        """, (wash_id,))
        row = await cursor.fetchone()
        if not row:
            await callback.answer("Мойка не найдена.")
            return
        slot_dur, break_dur, work_start, work_end, days_off_json = row
        days_off = json.loads(days_off_json) if days_off_json else []

    try:
        count = await generate_wash_slots(
            wash_id=wash_id,
            slot_duration=slot_dur,
            break_duration=break_dur,
            work_start=work_start,
            work_end=work_end,
            days_off=days_off,
            days=7
        )
        await callback.message.edit_text(f"✅ Слоты перегенерированы. Создано {count} новых слотов на ближайшие 7 дней.")
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка при генерации слотов: {e}")
    await callback.answer()


@router.callback_query(F.data == "close_settings")
async def close_settings(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.answer()


async def back_from_settings(message: Message, state: FSMContext):
    await state.clear()
    await wash_admin_panel(message, state)


# ---------- Статистика ----------
@router.message(F.text == "📊 Статистика")
async def wash_statistics(message: Message):
    if not await is_wash_admin(message.from_user.id):
        return

    user_id = message.from_user.id
    async with db.session() as conn:
        cursor = await conn.execute("SELECT id FROM car_washes WHERE admin_id = ?", (user_id,))
        wash_row = await cursor.fetchone()
        if not wash_row:
            await message.answer("Мойка не найдена.")
            return
        wash_id = wash_row[0]

        total_slots = (await conn.execute("SELECT COUNT(*) FROM wash_slots WHERE wash_id = ?", (wash_id,))).fetchone()[0]
        completed = (await conn.execute("SELECT COUNT(*) FROM wash_slots WHERE wash_id = ? AND progress = 'completed'", (wash_id,))).fetchone()[0]
        cancelled = (await conn.execute("SELECT COUNT(*) FROM wash_slots WHERE wash_id = ? AND status = 'free' AND user_id IS NOT NULL", (wash_id,))).fetchone()[0]
        avg_rating_row = await conn.execute("SELECT AVG(rating) FROM reviews WHERE entity_type = 'car_wash' AND entity_id = ? AND moderated = 1", (wash_id,))
        avg_rating = avg_rating_row.fetchone()[0]
        avg_rating = round(avg_rating, 2) if avg_rating else "нет оценок"

        text = (
            f"📊 Статистика мойки:\n"
            f"Всего слотов: {total_slots}\n"
            f"✅ Завершено моек: {completed}\n"
            f"❌ Отменено записей: {cancelled}\n"
            f"⭐ Средний рейтинг: {avg_rating}"
        )
        await message.answer(text)


# ---------- Генерация слотов ----------
@router.message(F.text == "🔄 Сгенерировать слоты")
async def generate_slots_handler(message: Message):
    if not await is_wash_admin(message.from_user.id):
        return

    user_id = message.from_user.id
    async with db.session() as conn:
        cursor = await conn.execute("""
            SELECT id, slot_duration, break_duration, work_start, work_end, days_off
            FROM car_washes WHERE admin_id = ?
        """, (user_id,))
        wash = await cursor.fetchone()
        if not wash:
            await message.answer("Мойка не найдена.")
            return
        wash_id, slot_dur, break_dur, work_start, work_end, days_off_json = wash
        days_off = json.loads(days_off_json) if days_off_json else []

    try:
        count = await generate_wash_slots(
            wash_id=wash_id,
            slot_duration=slot_dur,
            break_duration=break_dur,
            work_start=work_start,
            work_end=work_end,
            days_off=days_off,
            days=7
        )
        await message.answer(f"✅ Сгенерировано {count} новых слотов на ближайшие 7 дней.")
    except Exception as e:
        await message.answer(f"Ошибка при генерации слотов: {e}")


# ---------- Управление боксами (перенаправление на просмотр слотов) ----------
@router.message(F.text == "🔄 Управление боксами")
async def manage_boxes(message: Message, state: FSMContext):
    await view_slots(message, state)


# ========== ОБРАБОТЧИК ОЦЕНКИ МОЙКИ ==========
@router.callback_query(F.data.startswith("rate_wash_"))
async def process_rate_wash(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    if len(parts) != 4:
        await callback.answer("Ошибка данных")
        return
    slot_id = int(parts[2])
    rating = int(parts[3])

    async with db.session() as conn:
        # Находим wash_id по slot_id
        cursor = await conn.execute("SELECT wash_id FROM wash_slots WHERE id = ?", (slot_id,))
        row = await cursor.fetchone()
        if not row:
            await callback.answer("Ошибка: слот не найден.", show_alert=True)
            return
        wash_id = row[0]

        # Сохраняем отзыв
        cursor = await conn.execute(
            "INSERT INTO reviews (user_id, entity_type, entity_id, rating, comment, moderated, hidden) VALUES (?, 'car_wash', ?, ?, '', 0, 0)",
            (callback.from_user.id, wash_id, rating)
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