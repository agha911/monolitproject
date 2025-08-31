# monolitproject/backend/app/notifications/final_winners_broadcast.py
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Dict, Tuple

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.future import select

from app.bot_instance import bot
from app.database import async_session_maker
from app.models.user import User  # если у тебя другой путь, поправь импорт
from app.models.db_tournament_winner import TournamentWinner  # если другой путь к модели — поправь

# 🗓 Final period in DB (UTC naive): 18.08.2025 00:00 AZ → 01.09.2025 23:59 AZ
PERIOD_START = datetime(2025, 8, 17, 20, 0, 0)  # 18.08 00:00 (Asia/Baku)
PERIOD_END   = datetime(2025, 9,  1, 19, 59, 0)  # 01.09 23:59 (Asia/Baku)

# 💰 USDT rewards (Gold/Silver)
USDT_REWARD: Dict[Tuple[str, int], int] = {
    ("gold",   1): 30, ("gold",   2): 20, ("gold",   3): 10,
    ("silver", 1): 20, ("silver", 2): 15, ("silver", 3): 5,
}

LEAGUE_AZ = {"gold": "Qızıl", "silver": "Gümüş", "bronze": "Bürünc"}

def build_markup(winner_id: int) -> InlineKeyboardMarkup:
    """
    Кнопки для старта сбора данных (подарок/размер/кошелёк).
    Предполагается, что в основном боте уже зарегистрированы callback-хендлеры,
    которые понимают callback_data вида "prize:*".
    """
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("🎁 Termos",    callback_data=f"prize:thermos"),
        InlineKeyboardButton("🔋 Powerbank", callback_data=f"prize:powerbank"),
    )
    kb.add(
        InlineKeyboardButton("👕 Futbolka",  callback_data=f"prize:tshirt"),
    )
    return kb

def format_text_az(league: str, rank: int, clicks: int) -> str:
    league_az = LEAGUE_AZ.get(league, league.capitalize())
    reward = USDT_REWARD.get((league, rank))
    parts = [
        "🏆 *Təbriklər!* *Gappick* klik turnirində mükafatçısan.",
        f"Liqa: *{league_az}*",
        f"Yekun yer: *{rank}*",
        f"Kliklər: *{clicks}*",
        "",
        "🎁 Tərəfdaşımızdan hədiyyəni seç:",
        "• *Termos*  • *Powerbank*  • *Futbolka*",
        "Əgər futbolka seçsən — ölçünü göstərəcəksən.",
    ]
    if reward:
        parts += [
            "",
            f"💰 Əlavə olaraq sənə *{reward} USDT* verilir (şəbəkə: *TRC20*).",
            "Hədiyyəni seçdikdən sonra TRC20 ünvanını göndərəcəksən (\"T\" ilə başlayır).",
        ]
    parts += [
        "",
        "👇 Seçimə başlamaq üçün düymələrdən istifadə et.",
    ]
    return "\n".join(parts)

async def send_final_winners_broadcast():
    # 1) Получаем победителей финального периода
    async with async_session_maker() as session:
        q = await session.execute(
            select(TournamentWinner)
            .where(
                TournamentWinner.period_start == PERIOD_START,
                TournamentWinner.period_end   == PERIOD_END,
                TournamentWinner.rank_in_league <= 3,
            )
            .order_by(TournamentWinner.league, TournamentWinner.rank_in_league)
        )
        winners = q.scalars().all()

    if not winners:
        print("[INFO] tournament_winners is empty for the final period — nothing to send.")
        return

    # 2) Загружаем пользователей для telegram_id
    user_ids = [w.user_id for w in winners]
    users_map = {}
    async with async_session_maker() as session:
        uq = await session.execute(select(User).where(User.id.in_(user_ids)))
        for u in uq.scalars().all():
            users_map[u.id] = u

    # 3) Рассылка
    success, failed, skipped = 0, 0, 0
    for w in winners:
        u = users_map.get(w.user_id)
        if not u or not getattr(u, "telegram_id", None):
            skipped += 1
            continue

        text = format_text_az(w.league, int(w.rank_in_league), int(w.clicks_snapshot))
        markup = build_markup(winner_id=int(w.id))

        try:
            await bot.send_message(
                chat_id=int(u.telegram_id),
                text=text,
                parse_mode="Markdown",
                reply_markup=markup,
            )
            success += 1
            await asyncio.sleep(0.12)  # лёгкий троттлинг
        except Exception as e:
            print(f"[ERROR] send to {u.telegram_id}: {e}")
            failed += 1

    print(f"[DONE] Sent: {success}, failed: {failed}, skipped(no tg): {skipped}")

# 🚀 entrypoint
if __name__ == "__main__":
    asyncio.run(send_final_winners_broadcast())


# Хелпер для запуска из вашего кода (например, по команде/после финализации)
def start_notify_job(bot: TeleBot):
    asyncio.get_event_loop().create_task(notify_final_winners(bot))
