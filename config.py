import os
from dotenv import load_dotenv

load_dotenv()

# -------------------- BOT --------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не задан в .env")

# -------------------- OPENAI --------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# -------------------- ADMINS --------------------
def parse_admins(admins_str: str):
    if not admins_str:
        return []
    return [int(x) for x in admins_str.split(",") if x.strip().isdigit()]

ADMIN_IDS = parse_admins(os.getenv("ADMIN_IDS"))

# -------------------- DATABASE --------------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///avtomaster.db")

# -------------------- REDIS (для FSM) --------------------
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# -------------------- LOGGING --------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
