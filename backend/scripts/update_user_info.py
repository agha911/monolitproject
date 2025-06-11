import sys
import os

# Добавляем путь к корню проекта, чтобы заработали импорты вида from backend.app...
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
import requests
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.database import async_session_maker
from backend.app.models.user import User
from sqlalchemy import select

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or ""

def get_user_info_from_bot_api(user_id: int):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getChat"
    params = {"chat_id": user_id}
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if data.get("ok"):
            return data["result"]
    except Exception as e:
        print(f"[ERROR] Failed to fetch user {user_id}: {e}")
    return {}

async def update_missing_usernames(session: AsyncSession):
    result = await session.execute(select(User).where(User.username == None))
    users = result.scalars().all()
    print(f"🔍 Найдено {len(users)} пользователей без username")

    for user in users:
        info = get_user_info_from_bot_api(user.telegram_id)
        if info:
            user.username = info.get("username")
            user.first_name = info.get("first_name")
            user.last_name = info.get("last_name")
            print(f"✅ Обновлён {user.telegram_id}: @{user.username}")
    await session.commit()

async def update_referral_links(session: AsyncSession):
    result = await session.execute(select(User))
    users = result.scalars().all()
    count = 0

    for user in users:
        if user.invited_by and not user.invited_users:
            inviter = await session.get(User, user.invited_by)
            if inviter:
                inviter.invited_users.append(user)
                count += 1
    await session.commit()
    print(f"🔗 Обновлено связей: {count}")

async def main():
    async with async_session_maker() as session:
        await update_missing_usernames(session)
        await update_referral_links(session)

if __name__ == "__main__":
    asyncio.run(main())

