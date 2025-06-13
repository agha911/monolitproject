# backend/services/notifications.py

import httpx
from datetime import datetime, time, timezone, timedelta
from app.config import TELEGRAM_BOT_TOKEN

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# Временные рамки для уведомлений (UTC+4)
def is_within_notify_hours() -> bool:
    now = datetime.now(timezone.utc) + timedelta(hours=4)
    return time(10, 0) <= now.time() <= time(22, 0)

# Основная функция отправки сообщения
async def send_telegram_message(chat_id: str, text: str):
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{TELEGRAM_API}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown"
            }
        )

# === УВЕДОМЛЕНИЯ ПО ТИПАМ ===

async def notify_energy_full(user):
    """
    Уведомление о полном восстановлении энергии.
    Отправляется только один раз, если энергия достигла максимума.
    """
    if (
        user.energy == 100 and
        not user.energy_notified and
        is_within_notify_hours()
    ):
        await send_telegram_message(
            chat_id=user.telegram_id,
            text="⚡ *Enerjin tam bərpa olundu!* Qayıt və klik etməyə davam et 💥"
        )
        user.energy_notified = True

# Пример для будущих уведомлений:
# async def notify_daily_bonus(user): ...
