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
    "✨ *Gappick DAO test səsverməsi başladı!* ✨\n\n"
    "Art yarışmamızın yarımfinal və final mərhələlərində ən vacib səsvermələr "
    "Gappick tətbiqi daxilində, DAO sistemi vasitəsilə keçiriləcək. Buna görə indi "
    "*test səsverməsi* keçiririk ki, hər şey problemsiz işlədiyinə əmin olaq. 🧪🗳️\n\n"
    "📌 *Nə etmək lazımdır?*\n"
    "1️⃣ WebApp-i aç\n"
    "2️⃣ \"DAO\" səhifəsinə keç\n"
    "3️⃣ Maskot variantları arasında səs ver və sistemi yoxla ✅\n\n"
    "Bu, hələ *test mərhələsidir* — nəticələr əsas yarışmanın qalibini müəyyən etmir, "
    "amma gələcək yarımfinal və final səsvermələri üçün əsas olacaq.\n\n"
    "🙏 Senden xahişimiz:\n"
    "• Səs vermək üçün daxil ol\n"
    "• Əgər hər hansı bug və ya qəribəlik görsən, qrupda bizə yaz 🐞\n\n"
    "Gəlin birlikdə Gappick DAO səsvermə sistemini mükəmməlləşdirək! 🚀"
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






