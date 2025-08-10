from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update  # для reset_tournament_data
from typing import Optional, Tuple, Dict
from datetime import datetime, timedelta, timezone
from app.models.user import User
from app.models.app_stats import AppStats
from sqlalchemy.orm.attributes import flag_modified
from math import ceil

# --- НОВОЕ: безопасное получение пользователя для атомарных операций ---
async def get_user_for_update(session: AsyncSession, user_id: int) -> User:
    """
    Возвращает пользователя с блокировкой строки (SELECT ... FOR UPDATE).
    Используй внутри транзакции session.begin() / router уровень.
    """
    result = await session.execute(
        select(User).where(User.id == user_id).with_for_update()
    )
    return result.scalar_one()

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
    # нормализуем к naive UTC, чтобы не смешивать aware/naive
    def _as_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt
        return dt.astimezone(timezone.utc).replace(tzinfo=None)

    time = _as_naive_utc(time)

    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if user:
        user.energy = energy
        # В проекте используется camelCase в API — сохраняем совместимость
        # Модель может называться lastEnergyUpdate (как в фронте) или last_energy_update.
        if hasattr(user, "lastEnergyUpdate"):
            user.lastEnergyUpdate = time
        else:
            setattr(user, "last_energy_update", time)
        await session.commit()
        await session.refresh(user)

async def get_leaderboard(session: AsyncSession, limit: int = 50):
    result = await session.execute(
        select(User).order_by(User.total_xp.desc()).limit(limit)
    )
    return result.scalars().all()

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

async def increment_tournament_clicks(session: AsyncSession, telegram_id: int, amount: int):
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()

    if user:
        user.tournament_clicks = (user.tournament_clicks or 0) + amount
        session.add(user)
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
        .where(User.max_energy >= min_energy, User.max_energy <= max_energy)
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

async def increment_total_spent(session: AsyncSession, amount: int):
    result = await session.execute(select(AppStats).where(AppStats.id == 1))
    stats = result.scalar_one_or_none()

    if not stats:
        stats = AppStats(id=1, total_spent=0)
        session.add(stats)
        await session.commit()  # Коммитим создание записи

    stats.total_spent += amount
    await session.commit()

async def get_total_spent(session: AsyncSession) -> int:
    result = await session.execute(select(AppStats.total_spent).where(AppStats.id == 1))
    value = result.scalar()
    return value or 0

# =========================
# НОВОЕ: ЛОГИКА ДЛЯ БАТЧ-КЛИКОВ
# =========================

# --- НОВОЕ: унификация времени к naive UTC ---
def _as_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _get_last_energy_update(user: User) -> Optional[datetime]:
    # Совместимость с разными именами поля в модели
    if hasattr(user, "lastEnergyUpdate"):
        return user.lastEnergyUpdate
    return getattr(user, "last_energy_update", None)


def _set_last_energy_update(user: User, value: datetime) -> None:
    value = _as_naive_utc(value)  # всегда сохраняем naive UTC
    if hasattr(user, "lastEnergyUpdate"):
        user.lastEnergyUpdate = value
    else:
        setattr(user, "last_energy_update", value)


def recover_energy_inplace(user: User, now_utc: datetime) -> None:
    """
    Восстановление энергии “на лету” (8 часов до полного восстановления).
    Все расчёты ведём в naive UTC, чтобы не смешивать aware/naive.
    """
    max_energy = user.max_energy or 100
    if max_energy <= 0:
        max_energy = 100

    now_naive = _as_naive_utc(now_utc) or datetime.utcnow()

    last = _get_last_energy_update(user)
    if last is None:
        _set_last_energy_update(user, now_naive)
        return

    last_naive = _as_naive_utc(last) or datetime.utcnow()

    # Интервал восстановления одной единицы
    total_recovery_minutes = 480  # 8 часов
    interval_sec = (total_recovery_minutes * 60) / max(1, max_energy)

    delta_sec = (now_naive - last_naive).total_seconds()
    if delta_sec < 1:
        return

    units = int(delta_sec // interval_sec)
    if units <= 0:
        return

    before = int(user.energy or 0)
    user.energy = min(max_energy, before + units)

    used_sec = units * interval_sec
    new_last = last_naive + timedelta(seconds=used_sec)

    # Если дошли до максимума — синхронизируем таймштамп с текущим временем,
    # чтобы не накапливался “долг” восстановления
    if before < max_energy and user.energy == max_energy:
        _set_last_energy_update(user, now_naive)
    else:
        _set_last_energy_update(user, new_last)


async def apply_clicks_flush(
    session: AsyncSession,
    user: User,
    delta_clicks: int,
    client_seq: int,
    now_utc: Optional[datetime] = None
) -> Dict[str, int]:
    """
    Атомарно применяет пакет кликов с ИДЕМПОТЕНТНОСТЬЮ и СТРОГИМ порядком.
    Вызывай внутри открытой транзакции и после get_user_for_update().
    Возвращает словарь для ответа API.
    """
    # работаем с naive UTC, чтобы избежать TypeError (aware vs naive)
    now_utc = _as_naive_utc(now_utc) if now_utc else datetime.utcnow()

    # 1) Восстанавливаем энергию “на лету”
    recover_energy_inplace(user, now_utc)

    # 2) Идемпотентность и СТРОГИЙ порядок по client_seq
    last_seq = int(getattr(user, "last_client_seq", 0) or 0)
    client_seq = int(client_seq)

    if client_seq <= last_seq:
        # Дубликат/старый пакет — ничего не меняем
        return {
            "accepted_clicks": 0,
            "energy": int(user.energy or 0),
            "total_xp": int(user.total_xp or 0),
            "daily_progress": int(user.daily_progress or 0),
            "server_seq": last_seq,
        }

    if client_seq != last_seq + 1:
        # out-of-order — НЕ продвигаем последовательность, роутер вернёт NOOP
        raise ValueError("out_of_order_sequence")

    # 3) Сколько реально можем принять по энергии
    available = max(0, int(user.energy or 0))
    requested = max(0, int(delta_clicks))
    accepted = min(requested, available)

    

    if accepted > 0:
        user.energy = available - accepted                  # тратим «сырые» клики из энергии
        user.total_xp = int(user.total_xp or 0) + accepted # монеты по бусту
        user.daily_progress = int(user.daily_progress or 0) + accepted  # ежедневка по «сырым» кликам
        _set_last_energy_update(user, now_utc)              # фиксируем момент траты энергии

    # Продвигаем последовательность ТОЛЬКО на корректном next-seq
    setattr(user, "last_client_seq", client_seq)

    session.add(user)
    await session.flush()

    return {
        "accepted_clicks": accepted,
        "energy": int(user.energy or 0),
        "total_xp": int(user.total_xp or 0),
        "daily_progress": int(user.daily_progress or 0),
        "server_seq": int(getattr(user, "last_client_seq", 0) or 0),
    }


