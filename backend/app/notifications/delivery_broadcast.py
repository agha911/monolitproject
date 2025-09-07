# app/notifications/delivery_broadcast.py
from __future__ import annotations

import asyncio
from datetime import datetime
from sqlalchemy.future import select

from app.bot_instance import bot
from app.database import async_session_maker
from app.models.user import User
from app.models.db_tournament_winner import TournamentWinner

# --- финальный период турнира (UTC naive в БД) ---
PERIOD_START = datetime(2025, 8, 17, 20, 0, 0)  # 18.08 00:00 AZ
PERIOD_END   = datetime(2025, 9,  1, 19, 59, 0)  # 01.09 23:59 AZ

TEXT_AZ = (
    "📦 Çatdırılma üçün zəhmət olmasa aşağıdakı məlumatları göndər:\n\n"
    "1️⃣ Şəhər\n"
    "2️⃣ Küçə\n"
    "3️⃣ Ev\n"
    "4️⃣ Telefon nömrəsi (+994 ...)\n\n"
    "👉 Məlumatları bir mesajda yaz və göndər."
)

async def send_delivery_broadcast():
    # 1) Получаем всех победителей за период
    async with async_session_maker() as session:
        q = await session.execute(
            select(TournamentWinner)
            .where(
                TournamentWinner.period_start == PERIOD_START,
                TournamentWinner.period_end   == PERIOD_END,
                TournamentWinner.rank_in_league <= 3,
            )
        )
        winners = q.scalars().all()

    if not winners:
        print("[INFO] winners list empty — nothing to send.")
        return

    user_ids = [w.user_id for w in winners]
    users_map = {}
    async with async_session_maker() as session:
        uq = await session.execute(select(User).where(User.id.in_(user_ids)))
        for u in uq.scalars().all():
            users_map[u.id] = u

    success, failed, skipped = 0, 0, 0
    for w in winners:
        u = users_map.get(w.user_id)
        if not u or not getattr(u, "telegram_id", None):
            skipped += 1
            continue

        try:
            await bot.send_message(int(u.telegram_id), TEXT_AZ)
            success += 1
            await asyncio.sleep(0.15)
        except Exception as e:
            print(f"[ERROR] send to {u.telegram_id}: {e}")
            failed += 1

    print(f"[DONE] Sent: {success}, failed: {failed}, skipped: {skipped}")

if __name__ == "__main__":
    asyncio.run(send_delivery_broadcast())
