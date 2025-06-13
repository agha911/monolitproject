import asyncio
from datetime import datetime, time, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.database import async_session_maker
from app.models.user import User
from bot_instance import bot

def is_within_notify_hours() -> bool:
    now = datetime.now(timezone.utc) + timedelta(hours=4)  # UTC+4
    return time(10, 0) <= now.time() <= time(22, 0)

def send_sync_message(chat_id: int, text: str):
    try:
        bot.send_message(chat_id, text, parse_mode="Markdown")
        print(f"[NOTIFY] Sent to {chat_id}")
    except Exception as e:
        print(f"[ERROR] Failed to send message to {chat_id}: {e}")

async def send_telegram_message(chat_id: int, text: str):
    await asyncio.to_thread(send_sync_message, chat_id, text)

async def notify_energy_users():
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(
                User.energy_notified == False
            )
        )
        users = result.scalars().all()

        for user in users:
            # Учитываем бусты: сравниваем energy и user.max_energy
            if user.energy >= (user.max_energy or 100):
                if is_within_notify_hours():
                    await send_telegram_message(
                        chat_id=user.telegram_id,
                        text="⚡ *Enerjin tam bərpa olundu!* Qayıt və klik etməyə davam et 💥"
                    )
                    user.energy_notified = True
                    session.add(user)

        await session.commit()

async def background_notifier():
    while True:
        await notify_energy_users()
        await asyncio.sleep(600)  # 10 минут



