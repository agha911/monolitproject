from __future__ import annotations

import re
from datetime import datetime
from telebot.async_telebot import AsyncTeleBot
from telebot import types
from sqlalchemy import select, update, desc

from app.database import get_async_session
from app.models.db_tournament_winner import TournamentWinner
from app.models.user import User

# При желании можно оставить даты как "ограничитель окна",
# но для надёжности мы не фильтруем по точному равенству дат.

# Принимаем +994..., а также гибкие форматы с пробелами/скобками/дефисами (>=7 цифр)
PHONE_RE = re.compile(r"^\+?\d[\d\s\-()]{6,}$")

def _normalize_phone(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())

def _split_fields(text: str) -> list[str]:
    # Сначала режем по переводу строки/запятой/точке с запятой
    raw = [p.strip() for p in re.split(r"[\n,;]+", text) if p.strip()]
    # Иногда люди пишут "ул. Ахмадли 12" => хотим держать как единые части
    return raw

def register_delivery_handlers(bot: AsyncTeleBot):
    @bot.message_handler(content_types=["text"])
    async def _on_delivery(m: types.Message):
        try:
            text = (m.text or "").strip()
            parts = _split_fields(text)
            if len(parts) < 4:
                await bot.reply_to(
                    m,
                    "⚠️ Zəhmət olmasa bütün məlumatları göndər (şəhər, küçə, ev, telefon).\n"
                    "Nümunə:\nBakı, Nərimanov küç., 12, +994501234567"
                )
                return

            city, street, house, phone = parts[:4]
            phone = _normalize_phone(phone)

            if not PHONE_RE.fullmatch(phone):
                await bot.reply_to(m, "📞 Telefon düzgün formatda deyil. Nümunə: +994501234567")
                return

            # Находим последнюю запись победителя по telegram_id (без точного сравнения дат)
            async for session in get_async_session():
                q = await session.execute(
                    select(TournamentWinner, User)
                    .join(User, User.id == TournamentWinner.user_id)
                    .where(
                        User.telegram_id == m.chat.id,
                        TournamentWinner.rank_in_league <= 3,
                    )
                    .order_by(desc(TournamentWinner.created_at))
                    .limit(1)
                )
                row = q.first()
                if not row:
                    await bot.reply_to(m, "❌ Sizin məlumat tapılmadı. Admin ilə əlaqə saxlayın.")
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

                await bot.reply_to(
                    m,
                    "✅ Ünvan və telefon qeydə alındı.\n"
                    f"• Şəhər: {city}\n"
                    f"• Küçə: {street}\n"
                    f"• Ev: {house}\n"
                    f"• Telefon: {phone}\n"
                    "Təşəkkürlər!"
                )
                break

        except Exception as e:
            # Мягкое логирование + сообщение пользователю
            try:
                await bot.reply_to(m, "⚠️ Xəta baş verdi. Bir az sonra yenidən cəhd edin.")
            finally:
                print(f"[delivery_handlers] error for chat {m.chat.id}: {e}")

