# handlers/station_admin.py
import logging
from datetime import datetime
import os
import tempfile
import pandas as pd

from aiogram import Router, F, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

from database import db
from repositories.station_repo import StationRepository
from repositories.request_repo import RequestRepository
from states.admin_states import StationAdminStates
from states.client_states import ClientStates
from keyboards.reply import main_menu_kb, back_kb
from keyboards.inline import category_choice_kb, subcategory_choice_with_checkbox_kb
from utils.helpers import get_user_role, notify_regional_admin_about_review
from aiogram import Bot

STATUS_NAMES = {
    'new': '🆕 Новая',
    'accepted': '✅ Принята',
    'in_progress': '🔧 В работе',
    'completed': '✔️ Завершена',
    'cancelled': '❌ Отменена',
    'problem_not_resolved': '⚠️ Проблема не решена'
}

logger = logging.getLogger(__name__)
router = Router()

async def is_station_admin(user_id: int) -> bool:
    async with db.session() as conn:
        station_repo = StationRepository(conn)
        station = await station_repo.get_by_admin_id(user_id)
        return station is not None

# ---------- Просмотр заявок ----------
@router.message(F.text == "📋 Заявки СТО")
async def station_requests(message: Message, state: FSMContext):
    if not await is_station_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    user_id = message.from_user.id
    async with db.session() as conn:
        station_repo = StationRepository(conn)
        station = await station_repo.get_by_admin_id(user_id)
        if not station:
            await message.answer("Вы не привязаны ни к одному СТО.")
            return
        station_id = station.id
        request_repo = RequestRepository(conn)
        requests = await request_repo.get_by_station_id(station_id)
        if not requests:
            await message.answer("Нет активных заявок.")
            return

        for req in requests:
            client_info = await request_repo.get_client_info(req.user_id)
            status_display = STATUS_NAMES.get(req.status, req.status)
            text = (
                f"Заявка #{req.id}\n"
                f"Клиент: {client_info}\n"
                f"Описание: {req.description[:100]}\n"
                f"Статус: {status_display}\n"
            )
            if req.status == 'new':
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_sto_{req.id}")]
                ])
            else:
                kb = None
            await message.answer(text, reply_markup=kb)

# ---------- Принятие заявки ----------
@router.callback_query(F.data.startswith("accept_sto_"))
async def accept_request(callback: CallbackQuery):
    if not await is_station_admin(callback.from_user.id):
        await callback.answer("Нет прав")
        return
    request_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    async with db.session() as conn:
        request_repo = RequestRepository(conn)
        req = await request_repo.get_by_id(request_id)
        if not req or req.status != 'new':
            await callback.answer("Заявка уже не новая")
            return
        station_repo = StationRepository(conn)
        station = await station_repo.get_by_admin_id(user_id)
        if not station:
            await callback.answer("СТО не найдено")
            return
        station_id = station.id
        await request_repo.update(request_id, {
            "status": "accepted",
            "accepted_by": station_id,
            "accepted_at": datetime.now().isoformat()
        })
        await callback.bot.send_message(
            req.user_id,
            f"✅ Ваша заявка #{request_id} принята СТО."
        )
        await callback.message.edit_text(f"Заявка #{request_id} принята.")
        await callback.answer("Заявка принята")

# ---------- Отклонение заявки ----------
@router.callback_query(F.data.startswith("reject_"))
async def reject_request(callback: CallbackQuery):
    if not await is_station_admin(callback.from_user.id):
        await callback.answer("Нет прав")
        return
    request_id = int(callback.data.split("_")[1])
    async with db.session() as conn:
        request_repo = RequestRepository(conn)
        req = await request_repo.get_by_id(request_id)
        if not req:
            await callback.answer("Заявка не найдена")
            return
        await request_repo.update(request_id, {"status": "cancelled"})
        await callback.bot.send_message(
            req.user_id,
            f"❌ Ваша заявка #{request_id} отклонена СТО."
        )
        await callback.message.edit_text(f"Заявка #{request_id} отклонена.")
        await callback.answer("Заявка отклонена")

# ---------- Изменение статуса ----------
@router.message(F.text == "📌 Изменить статус")
async def change_status_prompt(message: Message, state: FSMContext):
    if not await is_station_admin(message.from_user.id):
        return
    await state.set_state(StationAdminStates.entering_request_id)
    await message.answer("Введите номер заявки:")

@router.message(StateFilter(StationAdminStates.entering_request_id))
async def change_status_request(message: Message, state: FSMContext):
    try:
        req_id = int(message.text)
    except ValueError:
        await message.answer("Неверный номер.")
        return
    user_id = message.from_user.id
    async with db.session() as conn:
        request_repo = RequestRepository(conn)
        req = await request_repo.get_by_id(req_id)
        if not req or req.accepted_by is None:
            await message.answer("Заявка не найдена.")
            return
        station_repo = StationRepository(conn)
        station = await station_repo.get_by_admin_id(user_id)
        if not station or req.accepted_by != station.id:
            await message.answer("Заявка не принадлежит вашему СТО.")
            return
        current_status = req.status
    await state.update_data(request_id=req_id, current_status=current_status)
    await state.set_state(StationAdminStates.choosing_new_status)
    kb = types.ReplyKeyboardMarkup(keyboard=[
        [types.KeyboardButton(text="В работе")],
        [types.KeyboardButton(text="Завершена")],
        [types.KeyboardButton(text="Проблема не решена")],
        [types.KeyboardButton(text="Отмена")]
    ], resize_keyboard=True)
    current_status_display = STATUS_NAMES.get(current_status, current_status)
    await message.answer(f"Текущий статус: {current_status_display}\nВыберите новый:", reply_markup=kb)

@router.message(StateFilter(StationAdminStates.choosing_new_status))
async def set_new_status(message: Message, state: FSMContext):
    new_status_map = {
        "В работе": "in_progress",
        "Завершена": "completed",
        "Проблема не решена": "problem_not_resolved",
        "Отмена": "cancelled"
    }
    if message.text not in new_status_map:
        await message.answer("Неверный выбор.")
        return
    new_status = new_status_map[message.text]
    data = await state.get_data()
    req_id = data['request_id']
    async with db.session() as conn:
        request_repo = RequestRepository(conn)
        await request_repo.update(req_id, {"status": new_status})
        if new_status == 'completed':
            await state.set_state(StationAdminStates.entering_amount)
            await message.answer("Введите сумму (в KZT):", reply_markup=main_menu_kb('station_admin'))
            await state.update_data(request_id=req_id)
            return
        await conn.commit()
        req = await request_repo.get_by_id(req_id)
        if req:
            client_text = {
                'in_progress': f"🔧 Статус вашей заявки #{req_id} изменён на «В работе».",
                'cancelled': f"❌ Заявка #{req_id} отменена СТО.",
                'problem_not_resolved': f"⚠️ По заявке #{req_id} возникла проблема. Свяжитесь с СТО."
            }.get(new_status)
            if client_text:
                await message.bot.send_message(req.user_id, client_text)
        new_status_display = STATUS_NAMES.get(new_status, new_status)
        await message.answer(f"Статус заявки #{req_id} изменён на {new_status_display}.", reply_markup=main_menu_kb('station_admin'))
        await state.clear()

@router.message(StateFilter(StationAdminStates.entering_amount))
async def process_amount(message: Message, state: FSMContext):
    try:
        amount = int(message.text)
    except ValueError:
        await message.answer("Введите целое число.")
        return
    data = await state.get_data()
    req_id = data['request_id']
    async with db.session() as conn:
        request_repo = RequestRepository(conn)
        await request_repo.update(req_id, {
            "status": "completed",
            "completed_at": datetime.now().isoformat(),
            "total_amount": amount
        })
        req = await request_repo.get_by_id(req_id)
        if req:
            await message.bot.send_message(
                req.user_id,
                f"✅ Заявка #{req_id} выполнена. Сумма: {amount} KZT\nОцените сервис:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=str(i), callback_data=f"rate_{req_id}_{i}") for i in range(1,6)]
                ])
            )
    await message.answer(f"Статус заявки #{req_id} изменён на «Завершена». Сумма {amount} KZT сохранена.")
    await state.clear()

# ---------- Обработка оценки ----------
@router.callback_query(lambda c: c.data.startswith("rate_") and len(c.data.split("_")) == 3)
async def process_rate(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    request_id = int(parts[1])
    rating = int(parts[2])

    async with db.session() as conn:
        request_repo = RequestRepository(conn)
        req = await request_repo.get_by_id(request_id)
        if not req or req.accepted_by is None:
            await callback.answer("Ошибка: исполнитель не определён.")
            return
        cursor = await conn.execute(
            "INSERT INTO reviews (user_id, entity_type, entity_id, rating, comment, moderated, hidden) VALUES (?, 'station', ?, ?, '', 0, 0)",
            (callback.from_user.id, req.accepted_by, rating)
        )
        review_id = cursor.lastrowid
        await conn.commit()

        await state.update_data(review_id=review_id, request_id=request_id)
        await state.set_state(ClientStates.waiting_for_review_text)

        await callback.message.edit_text(
            f"Спасибо за оценку {rating}⭐! Теперь вы можете оставить текстовый отзыв (или отправьте /пропустить)."
        )
        await callback.answer()

# ---------- Управление категориями СТО ----------
@router.message(F.text == "🛠 Управление категориями")
async def manage_categories(message: Message, state: FSMContext):
    if not await is_station_admin(message.from_user.id):
        return
    user_id = message.from_user.id
    async with db.session() as conn:
        cursor = await conn.execute("SELECT id, name FROM stations WHERE admin_id = ?", (user_id,))
        stations = await cursor.fetchall()
        if not stations:
            await message.answer("У вас нет СТО.")
            return
        station_id = stations[0][0]
        station_name = stations[0][1]
        # Исправлено: добавлен DISTINCT для устранения дублей
        cursor = await conn.execute('''
            SELECT DISTINCT c.id, c.name FROM categories c
            JOIN station_categories sc ON c.id = sc.category_id
            WHERE sc.station_id = ?
        ''', (station_id,))
        current_cats = await cursor.fetchall()
    text = f"🛠 Управление категориями для СТО «{station_name}»\n\n"
    if current_cats:
        text += "Текущие категории:\n" + "\n".join([f"• {cat[1]}" for cat in current_cats]) + "\n\n"
    else:
        text += "Список категорий пуст.\n\n"
    text += "Выберите действие:"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить категорию", callback_data="cat_add")],
        [InlineKeyboardButton(text="❌ Удалить категорию", callback_data="cat_remove")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="cat_back")]
    ])
    await state.update_data(station_id=station_id)
    await state.set_state(StationAdminStates.choosing_category_action)
    await message.answer(text, reply_markup=kb)

@router.callback_query(StateFilter(StationAdminStates.choosing_category_action), F.data == "cat_add")
async def category_add_start(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    station_id = data['station_id']
    async with db.session() as conn:
        cursor = await conn.execute("SELECT city_id FROM stations WHERE id = ?", (station_id,))
        city_row = await cursor.fetchone()
        if not city_row:
            await callback.answer("СТО не найдено")
            return
        city_id = city_row[0]
        cursor = await conn.execute('''
            SELECT id, name FROM categories
            WHERE city_id = ? AND id NOT IN (
                SELECT category_id FROM station_categories WHERE station_id = ?
            )
            ORDER BY name
        ''', (city_id, station_id))
        available = await cursor.fetchall()
    if not available:
        await callback.message.edit_text("Все категории уже добавлены. Новых нет.")
        await state.clear()
        await callback.answer()
        return
    # В category_add_start при формировании kb добавьте строку:
    kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text=cat[1], callback_data=f"cat_select_{cat[0]}")] for cat in available
    ] + [
        [InlineKeyboardButton(text="✅ Готово", callback_data="cat_done")],  # новая кнопка
        [InlineKeyboardButton(text="⬅ Назад", callback_data="cat_back")]
    ])
    await state.set_state(StationAdminStates.choosing_category_to_add)
    await callback.message.edit_text("Выберите категорию для добавления:", reply_markup=kb)
    await callback.answer()

@router.callback_query(StateFilter(StationAdminStates.choosing_category_to_add), F.data.startswith("cat_select_"))
async def category_add_execute(callback: CallbackQuery, state: FSMContext):
    cat_id = int(callback.data.split("_")[2])
    data = await state.get_data()
    station_id = data['station_id']
    async with db.session() as conn:
        # Проверка на существование
        check = await conn.execute(
            "SELECT 1 FROM station_categories WHERE station_id = ? AND category_id = ?",
            (station_id, cat_id)
        )
        if await check.fetchone():
            await callback.answer("❌ Эта категория уже добавлена.", show_alert=True)
            return
        try:
            await conn.execute('''
                INSERT INTO station_categories (station_id, category_id) VALUES (?, ?)
            ''', (station_id, cat_id))
            await conn.commit()
            await callback.answer("✅ Категория добавлена!", show_alert=False)
        except Exception as e:
            await callback.answer(f"❌ Ошибка: {e}", show_alert=True)
            return

    # Не очищаем состояние, а показываем обновлённый список доступных категорий
    await category_add_start(callback, state)
    await callback.answer()

@router.callback_query(StateFilter(StationAdminStates.choosing_category_action), F.data == "cat_remove")
async def category_remove_start(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    station_id = data['station_id']
    async with db.session() as conn:
        cursor = await conn.execute('''
            SELECT DISTINCT c.id, c.name FROM categories c
            JOIN station_categories sc ON c.id = sc.category_id
            WHERE sc.station_id = ?
        ''', (station_id,))
        current = await cursor.fetchall()
    if not current:
        await callback.message.edit_text("У этой станции нет категорий для удаления.")
        await state.clear()
        await callback.answer()
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"❌ {cat[1]}", callback_data=f"cat_remove_sel_{cat[0]}")] for cat in current
    ] + [[InlineKeyboardButton(text="⬅ Назад", callback_data="cat_back")]])
    await state.set_state(StationAdminStates.choosing_category_to_remove)
    await callback.message.edit_text("Выберите категорию для удаления:", reply_markup=kb)
    await callback.answer()

@router.callback_query(StateFilter(StationAdminStates.choosing_category_to_add), F.data == "cat_done")
async def category_add_done(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Возврат в меню управления категориями.")
    await callback.message.answer("Главное меню:", reply_markup=main_menu_kb('station_admin'))
    await callback.answer()    

@router.callback_query(StateFilter(StationAdminStates.choosing_category_to_remove), F.data.startswith("cat_remove_sel_"))
async def category_remove_execute(callback: CallbackQuery, state: FSMContext):
    cat_id = int(callback.data.split("_")[3])
    data = await state.get_data()
    station_id = data['station_id']
    async with db.session() as conn:
        await conn.execute('''
            DELETE FROM station_categories WHERE station_id = ? AND category_id = ?
        ''', (station_id, cat_id))
        await conn.commit()
    await callback.message.edit_text("✅ Категория успешно удалена.")
    await state.clear()
    await callback.answer()

@router.callback_query(StateFilter(StationAdminStates.choosing_category_action), F.data == "cat_back")
async def category_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Возврат в меню.")
    await callback.message.answer("Главное меню:", reply_markup=main_menu_kb('station_admin'))
    await callback.answer()

# ---------- Статистика СТО ----------
@router.message(F.text == "📊 Статистика СТО")
async def station_stats(message: Message):
    if not await is_station_admin(message.from_user.id):
        return
    user_id = message.from_user.id
    async with db.session() as conn:
        cursor = await conn.execute("SELECT id FROM stations WHERE admin_id=?", (user_id,))
        station = await cursor.fetchone()
        if not station:
            await message.answer("СТО не найдено")
            return
        station_id = station[0]
        cursor = await conn.execute("SELECT COUNT(*) FROM requests WHERE accepted_by=? AND status='completed'", (station_id,))
        completed = await cursor.fetchone()
        cursor = await conn.execute("SELECT COUNT(*) FROM requests WHERE accepted_by=?", (station_id,))
        total = await cursor.fetchone()
        cursor = await conn.execute(
            "SELECT AVG(rating) FROM reviews WHERE entity_type IN ('station', 'sto') AND entity_id=? AND moderated=1 AND hidden=0",
            (station_id,)
        )
        avg_rating = await cursor.fetchone()
    text = f"📊 Статистика СТО:\nВсего заявок: {total[0]}\nВыполнено: {completed[0]}\nСредний рейтинг: {avg_rating[0] if avg_rating[0] else 'нет'}"
    await message.answer(text)

# ---------- Загрузка прайс-листа ----------
@router.message(F.text == "📤 Загрузить прайс-лист")
async def upload_prices_start(message: Message, state: FSMContext):
    if not await is_station_admin(message.from_user.id):
        return
    await state.set_state(StationAdminStates.waiting_for_price_file)
    photo_path = "images/price_example.png"
    if os.path.exists(photo_path):
        photo = FSInputFile(photo_path)
        await message.answer_photo(
            photo=photo,
            caption="📎 **Отправьте Excel-файл с прайс-листом**\n\n"
                    "✅ Система принимает файлы только в формате **.xlsx** или **.xls**\n\n"
                    "📋 **Файл должен содержать 4 колонки с заголовками:**\n"
                    "• Марка\n"
                    "• Модель\n"
                    "• Услуга\n"
                    "• Цена\n\n"
                    "⚠️ **Важно:**\n"
                    "• Первая строка файла — это заголовки колонок\n"
                    "• В столбце «Цена» должны быть только числа (можно с пробелами)\n"
                    "• Лишние колонки будут проигнорированы\n\n"
                    "📤 **Отправьте файл, и я начну обработку**"
        )
    else:
        await message.answer(
            "📎 **Отправьте Excel-файл с прайс-листом**\n\n"
            "✅ Система принимает файлы только в формате **.xlsx** или **.xls**\n\n"
            "📋 **Файл должен содержать 4 колонки с заголовками:**\n"
            "• Марка\n"
            "• Модель\n"
            "• Услуга\n"
            "• Цена\n\n"
            "⚠️ **Важно:**\n"
            "• Первая строка файла — это заголовки колонок\n"
            "• В столбце «Цена» должны быть только числа (можно с пробелами)\n"
            "• Лишние колонки будут проигнорированы\n\n"
            "📤 **Отправьте файл, и я начну обработку**"
        )

@router.message(StateFilter(StationAdminStates.waiting_for_price_file), F.document)
async def handle_price_file(message: Message, state: FSMContext, bot: Bot):
    document = message.document
    if not document.file_name.endswith(('.xlsx', '.xls')):
        await message.answer("❌ Пожалуйста, отправьте файл в формате Excel (.xlsx или .xls)")
        return

    status_msg = await message.answer("⏳ Обрабатываем файл...")

    temp_fd, file_path = tempfile.mkstemp(suffix=".xlsx", prefix="prices_")
    os.close(temp_fd)
    await bot.download_file(document.file_id, file_path)

    async with db.session() as conn:
        cursor = await conn.execute('''
            SELECT s.id, c.name 
            FROM stations s 
            JOIN cities c ON s.city_id = c.id 
            WHERE s.admin_id = ?
        ''', (message.from_user.id,))
        station = await cursor.fetchone()
        if not station:
            await message.answer("❌ Ваше СТО не найдено в базе.")
            await state.clear()
            return
        station_id, city = station[0], station[1]

    try:
        count = await parse_and_insert_prices(file_path, station_id, city, message.from_user.id)
        await status_msg.edit_text(f"✅ Успешно загружено {count} услуг.")
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка при обработке файла: {e}")
    finally:
        os.remove(file_path)
        await state.clear()

async def parse_and_insert_prices(file_path: str, station_id: int, city: str, admin_id: int) -> int:
    """Парсит Excel и вставляет данные в station_services. Возвращает количество записей."""
    df = pd.read_excel(file_path, dtype=str)
    df.columns = [str(col).strip().lower() for col in df.columns]
    expected = ['марка', 'модель', 'услуга', 'цена']
    for col in expected:
        if col not in df.columns:
            raise ValueError(f"В файле не найдена колонка '{col}'")

    records = []
    for _, row in df.iterrows():
        brand = str(row['марка']).strip()
        model = str(row['модель']).strip()
        service = str(row['услуга']).strip()
        price_str = str(row['цена']).strip()

        if not brand or not model or not service or not price_str:
            continue

        price_clean = ''.join(c for c in price_str if c.isdigit())
        if not price_clean:
            continue
        price = int(price_clean)

        records.append((station_id, city, brand.lower(), model.lower(), service, price))

    if not records:
        return 0

    async with db.session() as conn:
        await conn.executemany('''
            INSERT INTO station_services 
            (station_id, city, brand, model, service_name, price)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', records)
        await conn.commit()

    return len(records)

# ---------- Обработчик кнопки "Моя ссылка" ----------
@router.message(F.text == "🔗 Моя ссылка")
async def my_referral_link(message: Message):
    user_id = message.from_user.id
    bot_username = (await message.bot.get_me()).username
    async with db.session() as conn:
        cursor = await conn.execute("SELECT id FROM stations WHERE admin_id = ?", (user_id,))
        station = await cursor.fetchone()
        if not station:
            await message.answer("❌ Ваше СТО не найдено в базе.")
            return
        station_id = station[0]
        ref_link = f"https://t.me/{bot_username}?start=ref_sto_{station_id}"
        await message.answer(
            f"🔗 Ваша персональная ссылка для привлечения клиентов:\n{ref_link}\n\n"
            "Поделитесь этой ссылкой – пользователи, перешедшие по ней, смогут быстро найти ваше СТО."
        )