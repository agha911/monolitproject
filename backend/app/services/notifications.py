# backend/services/notifications.py

from datetime import datetime, time, timezone, timedelta
import asyncio
from bot_instance import bot

# --- Настройки ---
MAX_ENERGY = 100  # Если у тебя где-то вынесено отдельно — импортируй

# --- Вспомогательная функция ---
def is_within_notify_hours() -> bool:
    now = datetime.now(timezone.utc) + timedelta(hours=4)  # UTC+4
    return time(10, 0) <= now.time() <= time(22, 0)

# --- Отправка уведомлений (в фоне) ---
def send_sync_message(chat_id: str, text: str):
    try:
        bot.send_message(chat_id, text, parse_mode="Markdown")
    except Exception as e:
        print(f"[ERROR] Failed to send message: {e}")

async def send_telegram_message(chat_id: str, text: str):
    await asyncio.to_thread(send_sync_message, chat_id, text)

# --- Уведомления по событиям ---
async def notify_energy_full(user):
    if (
        user.energy == MAX_ENERGY and
        not user.energy_notified and
        is_within_notify_hours()
    ):
        await send_telegram_message(
            chat_id=user.telegram_id,
            text="⚡ *Enerjin tam bərpa olundu!* Qayıt və klik etməyə davam et 💥"
        )
        user.energy_notified = True

