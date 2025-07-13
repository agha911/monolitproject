# app/notifications/send_manual_tournament_notify.py

from app.bot_instance import bot
from app.database import async_session_maker
from sqlalchemy.future import select
from app.models.user import User
import asyncio
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

TEXT = (
    "🏆 *Turnir başladı!*\n\n"
    "Dostlarını dəvət et və həftəlik turnirdə lider ol!\n"
    "👥 TOP-10 iştirakçı turnir səhifəsində göstərilir.\n\n"
    "🚀 Turnirə qatılmaq üçün aşağıdakı düyməyə kliklə:"
)

# Кнопка для запуска WebApp
markup = InlineKeyboardMarkup()
markup.add(
    InlineKeyboardButton(
        text="🚀 Turnirə keç", 
        web_app=WebAppInfo(url="https://monolitproject-5g7v.vercel.app/")
    )
)

async def send_tournament_announcement():
    async with async_session_maker() as session:
        result = await session.execute(select(User.telegram_id))
        telegram_ids = result.scalars().all()

    success, failed = 0, 0
    for tid in telegram_ids:
        try:
            await bot.send_message(
                chat_id=tid,
                text=TEXT,
                parse_mode="Markdown",
                reply_markup=markup
            )
            success += 1
        except Exception as e:
            print(f"[ERROR] {tid}: {e}")
            failed += 1

    print(f"[DONE] Sent: {success}, Failed: {failed}")

if __name__ == "__main__":
    asyncio.run(send_tournament_announcement())

