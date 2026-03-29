# handlers/settings.py
import logging
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from repositories.user_repo import UserRepository
from keyboards.reply import main_menu_kb
from utils.helpers import get_user_role

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.text == "⚙ Настройки")
async def settings_menu(message: Message, state: FSMContext):
    """Главное меню настроек: выбор отображения имени и смена города."""
    user_id = message.from_user.id
    async with db.session() as conn:
        user_repo = UserRepository(conn)
        user = await user_repo.get_by_telegram_id(user_id)
        current = user.display_name_choice if user else 'real_name'

    text = (
        "⚙ Настройки профиля\n\n"
        "Выберите, как будет отображаться ваше имя в отзывах:\n"
        "• Реальное имя – если оно указано в Telegram\n"
        "• Анонимно – просто «Пользователь»"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Реальное имя" + (" ✅" if current == 'real_name' else ""), callback_data="set_name_real")],
        [InlineKeyboardButton(text="🙈 Анонимно" + (" ✅" if current == 'anonymous' else ""), callback_data="set_name_anonymous")],
        [InlineKeyboardButton(text="🏙 Сменить город", callback_data="change_city")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="settings_back")]
    ])
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("set_name_"))
async def set_display_name(callback: CallbackQuery):
    """Обработчик выбора отображения имени."""
    choice = callback.data.split("_")[2]  # real или anonymous
    mapping = {'real': 'real_name', 'anonymous': 'anonymous'}
    new_choice = mapping.get(choice, 'real_name')
    user_id = callback.from_user.id
    async with db.session() as conn:
        await conn.execute(
            "UPDATE users SET display_name_choice = ? WHERE telegram_id = ?",
            (new_choice, user_id)
        )
        await conn.commit()

    await callback.answer("✅ Настройки сохранены", show_alert=False)

    # Обновляем сообщение, чтобы показать новую галочку
    async with db.session() as conn:
        cursor = await conn.execute(
            "SELECT display_name_choice FROM users WHERE telegram_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        current = row[0] if row else 'real_name'

    text = (
        "⚙ Настройки профиля\n\n"
        "Выберите, как будет отображаться ваше имя в отзывах:\n"
        "• Реальное имя – если оно указано в Telegram\n"
        "• Анонимно – просто «Пользователь»"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Реальное имя" + (" ✅" if current == 'real_name' else ""), callback_data="set_name_real")],
        [InlineKeyboardButton(text="🙈 Анонимно" + (" ✅" if current == 'anonymous' else ""), callback_data="set_name_anonymous")],
        [InlineKeyboardButton(text="🏙 Сменить город", callback_data="change_city")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="settings_back")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data == "change_city")
async def change_city_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик смены города."""
    from keyboards.inline import inline_city_choice
    await callback.message.edit_text(
        "Выберите новый город:",
        reply_markup=await inline_city_choice()
    )
    await callback.answer()


@router.callback_query(F.data == "settings_back")
async def settings_back(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню."""
    await callback.message.delete()
    role = await get_user_role(callback.from_user.id) or 'client'
    await callback.bot.send_message(
        chat_id=callback.from_user.id,
        text="⚙ Настройки сохранены. Главное меню:",
        reply_markup=main_menu_kb(role)
    )
    await callback.answer()