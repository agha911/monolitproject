import os
import requests
import asyncio
from sqlalchemy.future import select
from app.database import async_session_maker
from app.models.user import User

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

def get_user_info(telegram_id: int):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getChat"
    try:
        response = requests.get(url, params={"chat_id": telegram_id})
        data = response.json()
        if data.get("ok"):
            return data["result"]
    except Exception as e:
        print(f"[ERROR] Fetching user {telegram_id}: {e}")
    return {}

async def update_user_data():
    async with async_session_maker() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()

        id_map = {u.id: u for u in users}
        telegram_map = {u.telegram_id: u for u in users}

        for user in users:
            # 🧩 Обновим username, first_name, last_name если нужно
            if not user.username:
                info = get_user_info(user.telegram_id)
                if info:
                    user.username = info.get("username", user.username)
                    user.first_name = info.get("first_name", user.first_name)
                    user.last_name = info.get("last_name", user.last_name)

        # 🔄 Обновим обратные связи (если используешь relationship)
        for inviter in users:
            inviter.invited_users = [u for u in users if u.invited_by == inviter.id]

        await session.commit()
        print("✅ Пользователи обновлены")

if __name__ == "__main__":
    asyncio.run(update_user_data())
