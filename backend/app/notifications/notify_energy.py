import asyncio
from datetime import datetime, time
from sqlalchemy import select
from app.database import async_session_maker
from app.models.user import User
from app.bot_instance import bot  # импортируем общий bot

BAKU_TZ_OFFSET = 4  # UTC+4

async def notify_max_energy_users():
    now = datetime.utcnow().replace(tzinfo=None)
    current_hour = (now.hour + BAKU_TZ_OFFSET) % 24

    if current_hour < 10 or current_hour >= 22:
        print("[SKIP] Вне временного окна отправки уведомлений")
        return

    async with async_session_maker() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()

        count = 0
        for user in users:
            if (
                user.energy == user.max_energy and
                not user.energy_notified
            ):
                try:
                    await bot.send_message(
                        chat_id=user.telegram_id,
                        text="🔋 Sənin enerjin tam dolub! Yeni kliklər üçün hazırsan!"
                    )
                    user.energy_notified = True
                    session.add(user)
                    count += 1
                except Exception as e:
                    print(f"[ERROR] Не удалось отправить {user.telegram_id}: {e}")

        await session.commit()
        print(f"[DONE] Отправлено {count} уведомлений")


