# app/send_energy_notifications.py

from datetime import datetime, time as dt_time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.user import User
from app.database import async_session_maker
from app.bot_notifications import send_notification
import pytz

BAKU_TZ = pytz.timezone("Asia/Baku")

async def send_daily_energy_notifications():
    now_utc = datetime.utcnow()
    now_baku = now_utc.astimezone(BAKU_TZ)

    if not (dt_time(10, 0) <= now_baku.time() <= dt_time(22, 0)):
        print("[NOTIFY] Вне разрешённого временного окна")
        return

    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(
                User.energy == User.max_energy,
                User.energy_notified == False
            )
        )
        users = result.scalars().all()

        for user in users:
            try:
                send_notification(user.telegram_id, "⚡️ Enerjin tam dolub! Qəpik yığmağa davam et 💰")
                user.energy_notified = True
                session.add(user)
            except Exception as e:
                print(f"[NOTIFY ERROR] {user.telegram_id}: {e}")

        await session.commit()
        print(f"[NOTIFY] Уведомлений отправлено: {len(users)}")
