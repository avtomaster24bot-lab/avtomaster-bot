# keyboards/inline.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.helpers import stars_from_rating
from database import db

# ===== Общие =====
async def inline_city_choice():
    async with db.session() as conn:
        cursor = await conn.execute("SELECT id, name FROM cities ORDER BY name")
        rows = await cursor.fetchall()
    buttons = []
    for city_id, city_name in rows:
        buttons.append([InlineKeyboardButton(text=city_name, callback_data=f"city_{city_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ===== Для СТО =====
def category_choice_kb(categories):
    kb = []
    for cat in categories:
        kb.append([InlineKeyboardButton(text=cat.name, callback_data=f"cat_{cat.id}")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def subcategory_choice_with_checkbox_kb(subcategories, selected_ids=None):
    if selected_ids is None:
        selected_ids = []
    buttons = []
    for sub in subcategories:
        mark = "✅ " if sub.id in selected_ids else ""
        buttons.append([InlineKeyboardButton(text=f"{mark}{sub.name}", callback_data=f"sub_toggle_{sub.id}")])
    # Всегда добавляем кнопки Готово и Назад
    buttons.append([
        InlineKeyboardButton(text="✅ Готово", callback_data="sub_done"),
        InlineKeyboardButton(text="⬅ Назад", callback_data="sub_back")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ===== Для моек =====
def wash_list_kb(washes):
    kb = []
    for w_id, name, addr, rating in washes:
        stars = stars_from_rating(rating or 0)
        kb.append([InlineKeyboardButton(text=f"{name} {stars}", callback_data=f"wash_{w_id}")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

# ===== Для сервисной книжки =====
def cars_list_kb(cars):
    buttons = []
    for car_id, brand, model, year, license_plate in cars:
        text = f"{brand} {model} {year}" + (f" ({license_plate})" if license_plate else "")
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"car_{car_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ===== Для автопомощи =====
def roadside_services_kb(services, selected_ids=None):
    if selected_ids is None:
        selected_ids = []
    buttons = []
    for service_id, service_name in services:
        mark = "✅ " if service_id in selected_ids else ""
        buttons.append([InlineKeyboardButton(text=f"{mark}{service_name}", callback_data=f"roadside_toggle_{service_id}")])
    buttons.append([
        InlineKeyboardButton(text="✅ Готово", callback_data="roadside_done"),
        InlineKeyboardButton(text="⬅ Назад", callback_data="roadside_back")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ===== Для запчастей =====
def cancel_part_request_kb(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить заявку", callback_data=f"cancel_part_req:{request_id}")]
    ])

# ===== Для регистрации бизнеса =====
def partner_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔧 Автосервис (СТО)", callback_data="partner_type:sto")],
        [InlineKeyboardButton(text="🚿 Автомойка", callback_data="partner_type:wash")],
        [InlineKeyboardButton(text="🚨 Эвакуатор", callback_data="partner_type:tow")],
        [InlineKeyboardButton(text="📦 Поставщик запчастей", callback_data="partner_type:supplier")],
        [InlineKeyboardButton(text="🆘 Срочные услуги", callback_data="partner_type:urgent")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="partner:cancel")]
    ])

def supplier_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏪 Магазин", callback_data="supplier_type:shop")],
        [InlineKeyboardButton(text="🔧 Разборка", callback_data="supplier_type:dismantler")],
        [InlineKeyboardButton(text="🔨 Установщик", callback_data="supplier_type:installer")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="partner:back")]
    ])

def urgent_service_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔓 Вскрытие замков", callback_data="urgent_type:locksmith")],
        [InlineKeyboardButton(text="🛞 Выездной шиномонтаж", callback_data="urgent_type:tire")],
        [InlineKeyboardButton(text="📦 Доставка запчастей", callback_data="urgent_type:delivery")],
        [InlineKeyboardButton(text="⚡ Автоэлектрик", callback_data="urgent_type:electrician")],
        [InlineKeyboardButton(text="🔧 Мастер-универсал", callback_data="urgent_type:mechanic")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="partner:back")]
    ])

def yes_no_kb(callback_prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да", callback_data=f"{callback_prefix}:yes"),
         InlineKeyboardButton(text="❌ Нет", callback_data=f"{callback_prefix}:no")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="partner:back")]
    ])

def confirm_request_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отправить заявку", callback_data="partner:confirm")],
        [InlineKeyboardButton(text="🔄 Заполнить заново", callback_data="partner:restart")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="partner:cancel")]
    ])

def review_partner_request_kb(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"approve_partner:{request_id}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_partner:{request_id}")]
    ])