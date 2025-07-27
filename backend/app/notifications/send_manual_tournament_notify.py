from app.bot_instance import bot
from app.database import async_session_maker
from sqlalchemy.future import select
from app.models.user import User
import asyncio
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# 📩 Новый текст уведомления (единый для всех)
ANNOUNCEMENT_TEXT = (
    "🔔 *Vacib yeniliklər gəldi!*\n\n"
    "⚙️ Enerji sistemində iki önəmli dəyişiklik:\n"
    "1. Maksimum enerji artırıldıqda, artıq enerji avtomatik dolmur.\n"
    "2. Enerji hamı üçün *8 saata tam* bərpa olunur.\n\n"
    "🆕 Yeni gündəlik tapşırıq: klik et, nəticə göstər və *50 000 $GAP* qazan! Tapşırıq avtomatik qiymətləndirilir.\n\n"
    "📲 \"Tapşırıqlar\" bölməsində yoxla və yeniliklərdən yararlan!"
)

# 📌 Кнопки: переход в WebApp и раздел Tapşırıqlar
markup = InlineKeyboardMarkup()
markup.add(
    InlineKeyboardButton(
        text="🚀 Başla",
        web_app=WebAppInfo(url="https://monolitproject-5g7v.vercel.app/")
    ),
    InlineKeyboardButton(
        text="🎯 Tapşırıqlar",
        web_app=WebAppInfo(url="https://monolitproject-5g7v.vercel.app/tasks")
    )
)

# 📬 Основная функция рассылки
async def send_announcement_to_all():
    async with async_session_maker() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()

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
            print(f"[ERROR] {user.telegram_id}: {e}")
            failed += 1

    print(f"[DONE] Sent to {success} users, failed for {failed} users.")

# 🚀 Запуск
if __name__ == "__main__":
    asyncio.run(send_announcement_to_all())




