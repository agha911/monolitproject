# app/notifications/announce_art_contest.py

import asyncio
from sqlalchemy.future import select
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

from app.bot_instance import bot
from app.database import async_session_maker
from app.models.user import User

# 🔗 Instagram səhifəsi (qaydalar və iştirak)
INSTAGRAM_URL = "https://www.instagram.com/gap_pick?igsh=ZzdzYWE1MzgzNGJk&utm_source=qr"

# 🔔 Elan: Art Yarışması
ANNOUNCEMENT_TEXT = (
    "✨ *Art Yarışmamız başladı!* ✨\n"
    "🏆 *Baş mükafat: 300 USDT*\n\n"
    "Sən də öz yaradıcılığını göstər və Gappick maskotundan ilhamlanmış unikal "
    "T-shirt dizaynı yarat! 👕🪙\n\n"
    "📌 *Qaydalar çox sadədir:*\n"
    "1️⃣ Öz dizaynını hazırla\n"
    "2️⃣ Story-də paylaş\n"
    "3️⃣ Səhifəmizi qeyd et və «iştirak edirəm» yaz ✍️\n\n"
    "🔑 Yalnız *bir qalib* seçiləcək!\n\n"
    "Bu fürsəti qaçırma — yaradıcılığını hamıya göstər! 🚀"
)

def build_markup() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton(
            text="📸 Instagram səhifəsi",
            url=INSTAGRAM_URL
        )
    )
    markup.add(
        InlineKeyboardButton(
            text="🚀 Aç (WebApp)",
            web_app=WebAppInfo(url="https://monolitproject-5g7v.vercel.app/")
        )
    )
    return markup

async def send_announcement_to_all():
    async with async_session_maker() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()

    markup = build_markup()
    success, failed = 0, 0

    for user in users:
        try:
            await bot.send_message(
                chat_id=user.telegram_id,
                text=ANNOUNCEMENT_TEXT,
                parse_mode="Markdown",
                reply_markup=markup
            )
            success += 1
        except Exception as e:
            print(f"[ERROR] send to {user.telegram_id}: {e}")
            failed += 1
        await asyncio.sleep(0.03)

    print(f"[DONE] Sent to {success} users, failed for {failed} users.")

if __name__ == "__main__":
    asyncio.run(send_announcement_to_all())






