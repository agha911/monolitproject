# app/notifications/announce_referral_and_boost.py

import asyncio
from sqlalchemy.future import select
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

from app.bot_instance import bot
from app.database import async_session_maker
from app.models.user import User

# 🔔 Единое объявление про обновления
ANNOUNCEMENT_TEXT = (
    "🎉 *Gappick yenilikləri!*\n\n"
    "👥 *Yeni referal mexaniki*\n"
    "• Dəvət etdiyin hər aktiv istifadəçi üçün *10%* klik mükafatı qazanırsan.\n"
    "• Balans *istənilən anda* topladığını kleymləyə bilərsən.\n"
    "• Kleymlədikdən sonra *24 saatlıq pəncərə* başlayır — həmin müddətdə yenə toplayıb kleymlə.\n"
    "• Əgər *24 saat ərzində kleymləməsən*, o pəncərə bağlanır və yeni dövr sıfırdan başlayır.\n"
    "• *Dostlar* bölməsində balans və *geri sayım* göstərilir.\n\n"
    "💥 *Klik Busteri: x10-a qədər!*\n"
    "• Səviyyələr genişləndirildi: x1 → x10.\n"
    "• *Tələblər (6–10 səviyyə):*\n"
    "  — 6 səviyyə: *1* dəvət\n"
    "  — 7 səviyyə: *5* dəvət\n"
    "  — 8 səviyyə: *10* dəvət\n"
    "  — 9 səviyyə: *15* dəvət\n"
    "  — 10 səviyyə: *20* dəvət\n\n"
    "🛒 Busteri *Mağaza* bölməsindən al, tələbləri yerinə yetir və klikini gücləndir!\n\n"
    "🚀 *Yenilikləri indi sına!*"
)

# 📌 Кнопка: открыть WebApp
def build_markup() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton(
            text="🚀 Aç",
            web_app=WebAppInfo(url="https://monolitproject-5g7v.vercel.app/")
        )
    )
    return markup

async def send_announcement_to_all():
    # читаем всех пользователей одной сессией
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
            # Логируем и продолжаем, чтобы рассылка не останавливалась
            print(f"[ERROR] send to {user.telegram_id}: {e}")
            failed += 1
        # (опционально) небольшая пауза, чтобы смягчить rate-limit
        await asyncio.sleep(0.02)

    print(f"[DONE] Sent to {success} users, failed for {failed} users.")

if __name__ == "__main__":
    asyncio.run(send_announcement_to_all())





