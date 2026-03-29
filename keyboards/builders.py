# keyboards/builders.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Tuple, Optional

def build_pagination_kb(prefix: str, current_page: int, total_pages: int, extra_buttons: Optional[List[Tuple[str, str]]] = None) -> InlineKeyboardMarkup:
    """
    Построение пагинации.
    prefix – префикс для callback_data (например, "reviews_page")
    current_page – текущая страница (0-indexed)
    total_pages – общее количество страниц
    extra_buttons – список кортежей (text, callback_data) для дополнительных кнопок (например, "Назад")
    """
    buttons = []
    if current_page > 0:
        buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"{prefix}_{current_page-1}"))
    if current_page < total_pages - 1:
        buttons.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"{prefix}_{current_page+1}"))
    if buttons:
        row = buttons
    else:
        row = []
    kb = [row] if row else []
    if extra_buttons:
        for text, cb in extra_buttons:
            kb.append([InlineKeyboardButton(text=text, callback_data=cb)])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def build_rating_kb(request_id: int, entity_type: str = "sto") -> InlineKeyboardMarkup:
    """
    Клавиатура для оценки (1-5 звёзд).
    """
    buttons = []
    for i in range(1, 6):
        buttons.append(InlineKeyboardButton(text=str(i), callback_data=f"rate_{entity_type}_{request_id}_{i}"))
    return InlineKeyboardMarkup(inline_keyboard=[buttons])