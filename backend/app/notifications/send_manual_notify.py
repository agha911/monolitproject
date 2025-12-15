# app/notifications/send_manual_notify.py

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
    "🏁 *Gappick Art Yarışması – Final səsverməsi başladı!* 🏁\n\n"
    "Həlledici mərhələ artıq aktivdir. Son iki iş finalda üz-üzədir "
    "və qalib çox tezliklə müəyyən olunacaq.\n\n"
    "🗳️ İndi hər bir səs real təsir göstərir.\n"
    "💰 *Baş mükafat: 300 USDT*\n\n"
    "Finalın taleyi sənin qərarındadır. "
    "Səs ver və Gappick Art Yarışmasının qalibini birlikdə müəyyən edək.\n\n"
    "⏳ Vaxt məhduddur — final 24 saat davam edəcək."
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






