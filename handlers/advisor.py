# handlers/advisor.py
from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from repositories.user_repo import UserRepository
from states.client_states import ClientStates
from keyboards.reply import back_kb, main_menu_kb
from config import OPENAI_API_KEY
import openai
import logging

router = Router()

SYSTEM_PROMPT = """
Ты — опытный, спокойный и честный автомеханик с 20+ лет практики...
"""

@router.message(F.text == "💬 Спросить совет")
async def ask_advice(message: Message, state: FSMContext):
    await state.set_state(ClientStates.asking_advice)
    await message.answer(
        "Опишите проблему с вашим автомобилем, и я постараюсь помочь.",
        reply_markup=back_kb()
    )

@router.message(StateFilter(ClientStates.asking_advice))
async def advice_question_received(message: Message, state: FSMContext):
    user_question = message.text
    user_id = message.from_user.id

    async with db.session() as conn:
        user_repo = UserRepository(conn)
        user = await user_repo.get_by_telegram_id(user_id)
        city = user.city if user else None

        # Получить историю
        cursor = await conn.execute(
            "SELECT role, message FROM ai_chat_history WHERE user_id = ? ORDER BY created_at DESC LIMIT 5",
            (user_id,)
        )
        history_rows = await cursor.fetchall()
        history = list(reversed([{"role": r[0], "content": r[1]} for r in history_rows]))

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if city:
        messages.append({"role": "system", "content": f"Город пользователя: {city}"})
    messages.extend(history)
    messages.append({"role": "user", "content": user_question})

    try:
        if OPENAI_API_KEY:
            # Обновлённый синтаксис OpenAI API >=1.0
            client = openai.OpenAI(api_key=OPENAI_API_KEY)
            response = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages,
                temperature=0.7,
                max_tokens=800
            )
            answer = response.choices[0].message.content
        else:
            answer = "🔧 По вашему описанию похоже на проблему с системой зажигания. 🟡 Можно ехать аккуратно, но лучше проверить свечи и провода."
    except Exception as e:
        answer = "⚠️ В данный момент ИИ-советчик временно недоступен. Попробуйте позже."

    async with db.session() as conn:
        await conn.execute(
            "INSERT INTO ai_chat_history (user_id, role, message) VALUES (?, ?, ?)",
            (user_id, "user", user_question)
        )
        await conn.execute(
            "INSERT INTO ai_chat_history (user_id, role, message) VALUES (?, ?, ?)",
            (user_id, "assistant", answer)
        )
        await conn.commit()

    await message.answer(answer)
    await message.answer("Что хотите сделать дальше?", reply_markup=main_menu_kb('client'))
    await state.clear()