from app.bot_instance import bot
from app.database import async_session_maker
from sqlalchemy.future import select
from app.models.user import User
import asyncio
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

TEXT_WITH_INSTAGRAM = (
    "📸 *150 000 $GAP qazan!* Bizə Instagram-da abunə ol və tapşırığı yerinə yetir!\n\n"
    "➕ İndi *Telegram qrupumuza* da qoşula bilərsən — bu tapşırıq üçün də *150 000 $GAP* verilir!\n\n"
    "🎯 Hər iki tapşırığı \"Tapşırıqlar\" bölməsində tamamlaya bilərsən."
)

TEXT_ONLY_GROUP = (
    "💬 *Telegram qrupumuz artıq aktivdir!*\n\n"
    "Qrupa qoşul və yeni tapşırığı yerinə yetir — *150 000 $GAP* qazan!\n\n"
    "🎯 Tapşırığı \"Tapşırıqlar\" bölməsində tapa bilərsən."
)

# Кнопки: перейти в WebApp и в раздел Tapşırıqlar
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

INSTAGRAM_TASK_ID = "follow_instagram"

async def send_group_task_announcement():
    async with async_session_maker() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()

    success, failed = 0, 0
    for user in users:
        try:
            has_completed_instagram = INSTAGRAM_TASK_ID in (user.completed_tasks or [])
            text = TEXT_ONLY_GROUP if has_completed_instagram else TEXT_WITH_INSTAGRAM

            await bot.send_message(
                chat_id=user.telegram_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=markup
            )
            success += 1
        except Exception as e:
            print(f"[ERROR] {user.telegram_id}: {e}")
            failed += 1

    print(f"[DONE] Sent: {success}, Failed: {failed}")


if __name__ == "__main__":
    asyncio.run(send_group_task_announcement())



