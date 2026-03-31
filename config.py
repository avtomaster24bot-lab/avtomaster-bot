import os
from dotenv import load_dotenv

# Загружаем .env файл
load_dotenv()

# Токен бота
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан в переменных окружения")

# Админские ID через запятую, например "12345678,87654321"
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(","))) if os.getenv("ADMIN_IDS") else []

# База данных для SQLite
DATABASE_URL = os.getenv("DATABASE", "sqlite:///avtomaster.db")

# Уровень логирования
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")