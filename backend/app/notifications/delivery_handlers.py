# app/notifications/delivery_handlers.py
from __future__ import annotations

import re
from datetime import datetime
from telebot.async_telebot import AsyncTeleBot
from telebot import types
from sqlalchemy import select, update

from app.database import get_async_session
from app.models.db_tournament_winner import TournamentWinner
from app.models.user import User

PERIOD_START = datetime(2025, 8, 17, 20, 0, 0)
PERIOD_END   = datetime(2025, 9,  1, 19, 59, 0)

PHONE_RE = re.compile(r"^\+?\d[\d\s\-()]{6,}$")

def register_delivery_handlers(bot: AsyncTeleBot):
    @bot.message_handler(content_types=["text"])
    async def _on_delivery(m: types.Message):
        text = (m.text or "").strip()
        parts = [p.strip() for p in text.split("\n") if p.strip()]
        if len(parts) < 4:
            await bot.reply_to(m, "⚠️ Zəhmət olmasa bütün məlumatları göndər (şəhər, küçə, ev, telefon).")
            return

        city, street, house, phone = parts[:4]

        if not PHONE_RE.fullmatch(phone):
            await bot.reply_to(m, "📞 Telefon düzgün formatda deyil. Nümunə: +994501234567")
            return

        async for session in get_async_session():
            q = await session.execute(
                select(TournamentWinner, User)
                .join(User, User.id == TournamentWinner.user_id)
                .where(
                    User.telegram_id == m.chat.id,
                    TournamentWinner.period_start == PERIOD_START,
                    TournamentWinner.period_end == PERIOD_END,
                    TournamentWinner.rank_in_league <= 3,
                )
            )
            row = q.first()
            if not row:
                await bot.reply_to(m, "❌ Sizin məlumat tapılmadı.")
                break

            w, _u = row
            stmt = (
                update(TournamentWinner)
                .where(TournamentWinner.id == w.id)
                .values(
                    delivery_city=city,
                    delivery_street=street,
                    delivery_house=house,
                    delivery_phone=phone,
                    delivery_confirmed_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
            )
            await session.execute(stmt)
            await session.commit()
            await bot.reply_to(m, "✅ Ünvan və telefon qeydə alındı. Təşəkkürlər!")
            break
