import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан в переменных окружения")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Админские ID через запятую в .env, например: ADMIN_IDS=123456,789012
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(","))) if os.getenv("ADMIN_IDS") else []

# SQLite база для FSM
DATABASE_URL = os.getenv("DATABASE", "sqlite:///avtomaster.db")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")