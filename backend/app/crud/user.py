from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional
from datetime import datetime
from app.models.user import User
from sqlalchemy.orm.attributes import flag_modified
from math import ceil

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


async def mark_joined_group(session: AsyncSession, user: User, reward: int = 50):
    if user.joined_group:
        return False
    user.joined_group = True
    user.total_xp += reward
    await session.commit()
    await session.refresh(user)
    return True

async def assign_or_get_daily_task(session: AsyncSession, user: User):
    now = datetime.utcnow()
    today = now.date()

    # если задача уже создана сегодня — возвращаем её
    if user.daily_updated_at and user.daily_updated_at.date() == today:
        return {
            "daily_target": user.daily_target,
            "daily_progress": user.daily_progress,
            "daily_completed": user.daily_completed,
        }

    # иначе — пересчёт задачи
    min_energy = 100
    max_energy = 30000
    max_coeff = 3.5
    min_coeff = 1.2

    energy = user.max_energy or 100
    ratio = (energy - min_energy) / (max_energy - min_energy)
    coefficient = max_coeff - ratio * (max_coeff - min_coeff)

    target = ceil(energy * coefficient)

    user.daily_target = target
    user.daily_progress = 0
    user.daily_completed = False
    user.daily_reward_claimed = False
    user.daily_updated_at = now

    await session.commit()
    await session.refresh(user)

    return {
        "daily_target": target,
        "daily_progress": 0,
        "daily_completed": False,
    }


async def increment_tournament_clicks(session: AsyncSession, telegram_id: int, amount: int = 1):
    await session.execute(
        update(User)
        .where(User.telegram_id == telegram_id)
        .values(tournament_clicks=User.tournament_clicks + amount)
    )
    await session.commit()


# 2. Получение топа по лиге
async def get_tournament_leaderboard(session: AsyncSession, league: str):
    if league == "bronze":
        min_energy, max_energy = 5000, 15000
    elif league == "silver":
        min_energy, max_energy = 15000, 25000
    elif league == "gold":
        min_energy, max_energy = 25000, 30000
    else:
        raise ValueError("Invalid league")

    result = await session.execute(
        select(User)
        .where(User.max_energy >= min_energy, User.max_energy < max_energy)
        .order_by(User.tournament_clicks.desc())
        .limit(10)
    )
    return result.scalars().all()


# 3. Получение информации пользователя в турнире
async def get_user_tournament_info(session: AsyncSession, telegram_id: int):
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        return None

    if user.max_energy >= 25000:
        league = "gold"
        min_e, max_e = 25000, 30000
    elif user.max_energy >= 15000:
        league = "silver"
        min_e, max_e = 15000, 25000
    elif user.max_energy >= 5000:
        league = "bronze"
        min_e, max_e = 5000, 15000
    else:
        return {
            "league": None,
            "rank": None,
            "clicks": 0
        }

    result = await session.execute(
        select(User)
        .where(User.max_energy >= min_e, User.max_energy < max_e)
        .order_by(User.tournament_clicks.desc())
    )
    users = result.scalars().all()
    rank = next((i + 1 for i, u in enumerate(users) if u.telegram_id == telegram_id), None)

    return {
        "league": league,
        "rank": rank,
        "clicks": user.tournament_clicks
    }


# 4. Сброс всех турнирных кликов (раз в неделю)
async def reset_tournament_data(session: AsyncSession):
    await session.execute(
        update(User)
        .values(tournament_clicks=0, tournament_updated_at=datetime.utcnow())
    )
    await session.commit()
