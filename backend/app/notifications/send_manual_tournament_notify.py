from app.bot_instance import bot
from app.database import async_session_maker
from sqlalchemy.future import select
from app.models.user import User
import asyncio
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# 📩 Новый текст уведомления (единый для всех)
ANNOUNCEMENT_TEXT = (
    "🏆 *Yeni turnir sistemi aktivdir!*\n\n"
    "🥇 İndi Həftəlik Turnir *3 liqa* üzrə keçiriləcək:\n"
    "• *Qızıl liqa* – ən güclülər (Maks. enerji >25.000)\n"
    "• *Gümüş liqa* – inkişaf yolunda olanlar (15.000 > Maks. enerji < 25.000)\n"
    "• *Bürünc liqa* – yeni başlayanlar (5.000 > Maks. enerji < 15.000)\n\n"
    "📊 Mövqe və klik sayı *turnir səhifəsində* əks olunur.\n\n"
    "🧪 Bu həftə *test dövrüdür*. Tətbiqdə tapılan hər *səhv üçün 100 000 $GAP* mükafat verilir!\n\n"
    "💰 Bundan əlavə, artıq *ümumi $GAP Fondu* hesablanır — bütün oyunçuların xərclədiyi vəsait birgə fonda toplanır.\n\n"
    "🚀 Yenilikləri kəşf et və öz liqanı fəth et!"
)

# 📌 Кнопки: переход в WebApp и раздел Tapşırıqlar
markup = InlineKeyboardMarkup()
markup.add(
    InlineKeyboardButton(
        text="🚀 Başla",
        web_app=WebAppInfo(url="https://monolitproject-5g7v.vercel.app/")
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




