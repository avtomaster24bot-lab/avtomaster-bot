from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def main_menu_kb(role: str = 'client'):
    role = role.strip().lower()
    if role == 'client':
        kb = [
            [KeyboardButton(text="🚨 Эвакуатор")],
            [KeyboardButton(text="🚗 Найти автосервис"), KeyboardButton(text="🛒 Запчасти")],
            [KeyboardButton(text="🚿 Автомойка"), KeyboardButton(text="🆘 Автопомощь")],
            [KeyboardButton(text="💬 Спросить совет"), KeyboardButton(text="💰 Узнать цену")],
            [KeyboardButton(text="📊 История заявок"), KeyboardButton(text="📒 Сервисная книжка")],
            [KeyboardButton(text="⭐ Мои отзывы"), KeyboardButton(text="⚙ Настройки")],
            [KeyboardButton(text="💼 Для бизнеса")]
        ]
    elif role == 'station_admin':
        kb = [
            [KeyboardButton(text="📋 Заявки СТО")],
            [KeyboardButton(text="📌 Изменить статус")],
            [KeyboardButton(text="🛠 Управление категориями")],
            [KeyboardButton(text="📊 Статистика СТО")],
            [KeyboardButton(text="📤 Загрузить прайс-лист")],
            [KeyboardButton(text="🔗 Моя ссылка")],
            [KeyboardButton(text="⬅ Главное меню")]
        ]
    elif role == 'wash_admin':
        kb = [
            [KeyboardButton(text="🚿 Управление мойкой")],
            [KeyboardButton(text="🔗 Моя ссылка")],
            [KeyboardButton(text="⬅ Главное меню")]
        ]
    elif role == 'tow_admin':
        kb = [
            [KeyboardButton(text="🚨 Мои заявки")],
            [KeyboardButton(text="🔗 Моя ссылка")],
            [KeyboardButton(text="⬅ Главное меню")]
        ]
    elif role == 'regional_admin':
        kb = [
            [KeyboardButton(text="🏙 Панель регионального админа")],
            [KeyboardButton(text="📋 Список СТО")],
            [KeyboardButton(text="📋 Список поставщиков")],
            [KeyboardButton(text="📋 Список эвакуаторов")],
            [KeyboardButton(text="📤 Загрузить прайс для СТО")],
            [KeyboardButton(text="⬅ Главное меню")]
        ]
    elif role == 'global_admin':
        kb = [
            [KeyboardButton(text="🌍 Панель главного админа")],
            [KeyboardButton(text="⬅ Главное меню")]
        ]
    elif role == 'supplier':
        kb = [
            [KeyboardButton(text="📦 Мои заявки на запчасти")],
            [KeyboardButton(text="💰 Мои предложения")],
            [KeyboardButton(text="🔗 Моя ссылка")],
            [KeyboardButton(text="⬅ Главное меню")]
        ]
    elif role == 'service_provider':
        kb = [
            [KeyboardButton(text="📋 Мои заявки")],
            [KeyboardButton(text="🔗 Моя ссылка")],
            [KeyboardButton(text="⬅ Главное меню")]
        ]
    else:
        kb = [[KeyboardButton(text="⬅ Главное меню")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def back_kb():
    kb = [[KeyboardButton(text="⬅ Назад")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)