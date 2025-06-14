import asyncio
from sqlalchemy import select
from app.database import async_session_maker
from app.models.user import User

async def reset_instagram_task():
    async with async_session_maker() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()

        for user in users:
            if "follow_instagram" in user.completed_tasks:
                user.completed_tasks = [
                    task for task in user.completed_tasks if task != "follow_instagram"
                ]
                session.add(user)

        await session.commit()
        print("[RESET] follow_instagram удалено у всех пользователей")

if __name__ == "__main__":
    asyncio.run(reset_instagram_task())
