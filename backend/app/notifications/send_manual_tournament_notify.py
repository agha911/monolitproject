# app/notifications/send_manual_tournament_notify.py

from app.bot_instance import bot
from app.database import async_session_maker
from sqlalchemy.future import select
from app.models.user import User
import asyncio
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

TEXT = (
    "🛠 *Yenilənmə tamamlandı!*\n\n"
    "🔁 Bütün istifadəçilərin irəliləyiş problemi həll edildi və sistem sabitləşdirildi.\n"
    "💰 Kompensasiya olaraq hər kəsə *100 000 $GAP* balansına əlavə olundu.\n\n"
    "🏆 *Turnir başladı!*\n"
    "Dostlarını dəvət et və həftəlik turnirdə lider ol! TOP-10 iştirakçı turnir səhifəsində göstərilir.\n"
    "🎁 Turnirdə *real mükafatlar* səni gözləyir!\n\n"
    "📸 *Instagram-da bizi izləməyi unutma!* Bu addımı \"Tapşırıqlar\" bölməsində yerinə yetirib bonus qazana bilərsən: @gappick.app\n\n"
    "🚀 Turnirə qatılmaq və tapşırıqları yerinə yetirmək üçün aşağıdakı düymələrdən istifadə et:"
)

# Кнопки: перейти в WebApp и в раздел Tapşırıqlar
markup = InlineKeyboardMarkup()
markup.add(
    InlineKeyboardButton(
        text="🚀 Turnirə keç",
        web_app=WebAppInfo(url="https://monolitproject-5g7v.vercel.app/")
    ),
    InlineKeyboardButton(
        text="🎯 Tapşırıqlar",
        web_app=WebAppInfo(url="https://monolitproject-5g7v.vercel.app/tasks")
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

