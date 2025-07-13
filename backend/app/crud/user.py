from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional
from datetime import datetime
from app.models.user import User
from sqlalchemy.orm.attributes import flag_modified

MAX_ENERGY_CAP = 30000
ENERGY_INCREMENT = 100
ENERGY_UPGRADE_COST = 500


async def get_user(session: AsyncSession, telegram_id: int):
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()

async def create_user(
    session: AsyncSession,
    user_id: int,
    username: str,
    first_name: str,
    last_name: str,
    invited_by: Optional[int] = None
) -> User:
    user = User(
        id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        invited_by=invited_by
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user

async def update_progress(
    session: AsyncSession,
    telegram_id: int,
    energy: int,
    total_xp: int
):
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if user:
        user.energy = energy
        user.total_xp = total_xp
        await session.commit()
        await session.refresh(user)

async def update_energy_and_time(
    session: AsyncSession,
    telegram_id: int,
    energy: int,
    time: datetime
):
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if user:
        user.energy = energy
        user.lastEnergyUpdate = time
        await session.commit()
        await session.refresh(user)

async def get_leaderboard(session: AsyncSession, limit: int = 50):
    result = await session.execute(
        select(User).order_by(User.total_xp.desc()).limit(limit)
    )
    return result.scalars().all()

async def buy_max_energy(session: AsyncSession, user: User) -> bool:
    if user.max_energy >= MAX_ENERGY_CAP:
        return False

    if user.total_xp < ENERGY_UPGRADE_COST:
        return False

    user.total_xp -= ENERGY_UPGRADE_COST
    user.max_energy += ENERGY_INCREMENT

    if user.energy < user.max_energy:
        user.energy = user.max_energy

    session.add(user)
    await session.commit()
    return True

async def complete_task(session: AsyncSession, user: User, task_id: str, reward: int = 50):
    if task_id in user.completed_tasks:
        return False
    user.completed_tasks.append(task_id)
    flag_modified(user, "completed_tasks")
    user.total_xp += reward
    await session.commit()
    await session.refresh(user)
    return True

async def daily_checkin(session: AsyncSession, user: User, now: datetime, reward: int, streak: int):
    user.last_checkin = now
    user.daily_streak = streak
    user.total_xp += reward
    await session.commit()
    await session.refresh(user)
    return user


