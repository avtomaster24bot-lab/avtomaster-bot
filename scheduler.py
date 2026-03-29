# scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
import logging
from database import db

logger = logging.getLogger(__name__)   # IMPROVEMENT
scheduler = AsyncIOScheduler()

async def check_reminders(bot):
    """Проверка напоминаний: за 1 час до записи на мойку (отправляет только один раз)."""
    now = datetime.now()
    one_hour_later = now + timedelta(hours=1)

    logger.info(f"Проверка напоминаний: сейчас {now}, ищем слоты между {now} и {one_hour_later}")  # вместо print

    async with db.session() as conn:
        rows = await conn.execute("""
            SELECT wash_slots.id, wash_slots.user_id, wash_slots.datetime, car_washes.name, car_washes.admin_id
            FROM wash_slots
            JOIN car_washes ON wash_slots.wash_id = car_washes.id
            WHERE wash_slots.status = 'booked' 
              AND (wash_slots.reminder_sent IS NULL OR wash_slots.reminder_sent = 0)
              AND datetime(wash_slots.datetime) >= datetime(?)
              AND datetime(wash_slots.datetime) < datetime(?)
        """, (now.isoformat(), one_hour_later.isoformat()))
        slots = await rows.fetchall()

        logger.info(f"Найдено слотов для напоминания: {len(slots)}")  # вместо print

        for slot_id, user_id, dt_str, wash_name, admin_id in slots:
            await bot.send_message(user_id, f"⏰ Напоминание: через 1 час у вас запись на мойку '{wash_name}' в {dt_str}")
            if admin_id:
                await bot.send_message(admin_id, f"⏰ Напоминание: через 1 час клиент приедет на мойку '{wash_name}'")
            await conn.execute("UPDATE wash_slots SET reminder_sent = 1 WHERE id = ?", (slot_id,))
        await conn.commit()

def start_scheduler(bot):
    scheduler.add_job(check_reminders, IntervalTrigger(minutes=1), args=[bot])
    scheduler.start()