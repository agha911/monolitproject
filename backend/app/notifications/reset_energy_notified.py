import asyncio
from sqlalchemy import select
from app.database import async_session_maker
from app.models.user import User

async def reset_energy_flags():
    async with async_session_maker() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()

        for user in users:
            user.energy_notified = False
            session.add(user)

        await session.commit()
        print("[RESET] energy_notified сброшены у всех пользователей")

if __name__ == "__main__":
    asyncio.run(reset_energy_flags())
