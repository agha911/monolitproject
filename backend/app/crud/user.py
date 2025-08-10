import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update  # для reset_tournament_data
from typing import Optional, Tuple, Dict
from datetime import datetime, timedelta, timezone
from app.models.user import User
from app.models.app_stats import AppStats
from sqlalchemy.orm.attributes import flag_modified
from math import ceil

log = logging.getLogger("app")
clicks_log = logging.getLogger("app.clicks")
energy_log = logging.getLogger("app.energy")
tournament_log = logging.getLogger("app.tournament")
daily_log = logging.getLogger("app.daily")
users_log = logging.getLogger("app.users")
stats_log = logging.getLogger("app.stats")

# --- НОВОЕ: безопасное получение пользователя для атомарных операций ---
async def get_user_for_update(session: AsyncSession, user_id: int) -> User:
    """
    Возвращает пользователя с блокировкой строки (SELECT ... FOR UPDATE).
    Используй внутри транзакции session.begin() / router уровень.
    """
    users_log.debug("users.get_user_for_update.start", extra={"user_id": user_id})
    result = await session.execute(
        select(User).where(User.id == user_id).with_for_update()
    )
    user = result.scalar_one()
    users_log.info("users.get_user_for_update.ok", extra={"user_id": user_id})
    return user

async def get_user(session: AsyncSession, telegram_id: int):
    users_log.debug("users.get_user.start", extra={"telegram_id": telegram_id})
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    users_log.info(
        "users.get_user.%s",
        "found" if user else "none",
        extra={"telegram_id": telegram_id, "found": bool(user)},
    )
    return user

async def create_user(
    session: AsyncSession,
    user_id: int,
    username: str,
    first_name: str,
    last_name: str,
    invited_by: Optional[int] = None
) -> User:
    users_log.info(
        "users.create_user.start",
        extra={"user_id": user_id, "username": username, "invited_by": invited_by},
    )
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
    users_log.info("users.create_user.ok", extra={"user_id": user_id})
    return user

async def update_progress(
    session: AsyncSession,
    telegram_id: int,
    energy: int,
    total_xp: int
):
    users_log.info(
        "users.update_progress.start",
        extra={"telegram_id": telegram_id, "energy": energy, "total_xp": total_xp},
    )
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if user:
        before = {"energy": int(user.energy or 0), "total_xp": int(user.total_xp or 0)}
        user.energy = energy
        user.total_xp = total_xp
        await session.commit()
        await session.refresh(user)
        users_log.info(
            "users.update_progress.ok",
            extra={"telegram_id": telegram_id, "before": before, "after": {"energy": energy, "total_xp": total_xp}},
        )
    else:
        users_log.warning("users.update_progress.not_found", extra={"telegram_id": telegram_id})

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

    users_log.info(
        "users.update_energy_and_time.start",
        extra={"telegram_id": telegram_id, "energy": energy, "time": str(time)},
    )
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if user:
        before_energy = int(user.energy or 0)
        before_leu = getattr(user, "lastEnergyUpdate", None) or getattr(user, "last_energy_update", None)
        user.energy = energy
        if hasattr(user, "lastEnergyUpdate"):
            user.lastEnergyUpdate = time
        else:
            setattr(user, "last_energy_update", time)
        await session.commit()
        await session.refresh(user)
        users_log.info(
            "users.update_energy_and_time.ok",
            extra={"telegram_id": telegram_id, "energy_before": before_energy, "energy_after": energy, "leu_before": str(before_leu), "leu_after": str(time)},
        )
    else:
        users_log.warning("users.update_energy_and_time.not_found", extra={"telegram_id": telegram_id})

async def get_leaderboard(session: AsyncSession, limit: int = 50):
    users_log.debug("users.get_leaderboard.start", extra={"limit": limit})
    result = await session.execute(
        select(User).order_by(User.total_xp.desc()).limit(limit)
    )
    rows = result.scalars().all()
    users_log.info("users.get_leaderboard.ok", extra={"limit": limit, "count": len(rows)})
    return rows

async def complete_task(session: AsyncSession, user: User, task_id: str, reward: int = 50):
    daily_log.info("daily.complete_task.start", extra={"user_id": user.id, "task_id": task_id})
    if task_id in user.completed_tasks:
        daily_log.info("daily.complete_task.already_done", extra={"user_id": user.id, "task_id": task_id})
        return False
    before = int(user.total_xp or 0)
    user.completed_tasks.append(task_id)
    flag_modified(user, "completed_tasks")
    user.total_xp = before + reward
    await session.commit()
    await session.refresh(user)
    daily_log.info(
        "daily.complete_task.ok",
        extra={"user_id": user.id, "task_id": task_id, "reward": reward, "xp_before": before, "xp_after": int(user.total_xp or 0)},
    )
    return True

async def daily_checkin(session: AsyncSession, user: User, now: datetime, reward: int, streak: int):
    daily_log.info("daily.checkin.start", extra={"user_id": user.id, "streak": streak, "reward": reward})
    before = int(user.total_xp or 0)
    user.last_checkin = now
    user.daily_streak = streak
    user.total_xp = before + reward
    await session.commit()
    await session.refresh(user)
    daily_log.info("daily.checkin.ok", extra={"user_id": user.id, "xp_before": before, "xp_after": int(user.total_xp or 0)})
    return user

async def mark_joined_group(session: AsyncSession, user: User, reward: int = 50):
    daily_log.info("daily.joined_group.start", extra={"user_id": user.id})
    if user.joined_group:
        daily_log.info("daily.joined_group.already", extra={"user_id": user.id})
        return False
    before = int(user.total_xp or 0)
    user.joined_group = True
    user.total_xp = before + reward
    await session.commit()
    await session.refresh(user)
    daily_log.info("daily.joined_group.ok", extra={"user_id": user.id, "xp_before": before, "xp_after": int(user.total_xp or 0)})
    return True

async def assign_or_get_daily_task(session: AsyncSession, user: User):
    now = datetime.utcnow()
    today = now.date()

    # если задача уже создана сегодня — возвращаем её
    if user.daily_updated_at and user.daily_updated_at.date() == today:
        daily_log.info(
            "daily.assign_or_get.reuse",
            extra={"user_id": user.id, "target": user.daily_target, "progress": user.daily_progress, "completed": user.daily_completed},
        )
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

    before = {"target": user.daily_target, "progress": user.daily_progress}
    user.daily_target = target
    user.daily_progress = 0
    user.daily_completed = False
    user.daily_reward_claimed = False
    user.daily_updated_at = now

    await session.commit()
    await session.refresh(user)

    daily_log.info(
        "daily.assign_or_get.new",
        extra={
            "user_id": user.id,
            "max_energy": energy,
            "coefficient": coefficient,
            "target": target,
            "before": before,
        },
    )

    return {
        "daily_target": target,
        "daily_progress": 0,
        "daily_completed": False,
    }

async def increment_tournament_clicks(session: AsyncSession, telegram_id: int, amount: int):
    tournament_log.info("tournament.increment_clicks.start", extra={"telegram_id": telegram_id, "amount": amount})
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()

    if user:
        before = int(user.tournament_clicks or 0)
        user.tournament_clicks = before + amount
        user.tournament_updated_at = datetime.utcnow()
        session.add(user)
        await session.commit()
        tournament_log.info(
            "tournament.increment_clicks.ok",
            extra={"telegram_id": telegram_id, "before": before, "after": int(user.tournament_clicks or 0)},
        )
    else:
        tournament_log.warning("tournament.increment_clicks.not_found", extra={"telegram_id": telegram_id})

# 2. Получение топа по лиге
async def get_tournament_leaderboard(session: AsyncSession, league: str):
    if league == "bronze":
        min_energy, max_energy = 5000, 15000
    elif league == "silver":
        min_energy, max_energy = 15000, 25000
    elif league == "gold":
        min_energy, max_energy = 25000, 30000
    else:
        tournament_log.error("tournament.leaderboard.invalid_league", extra={"league": league})
        raise ValueError("Invalid league")

    tournament_log.debug("tournament.leaderboard.start", extra={"league": league, "min": min_energy, "max": max_energy})
    result = await session.execute(
        select(User)
        .where(User.max_energy >= min_energy, User.max_energy <= max_energy)
        .order_by(User.tournament_clicks.desc())
        .limit(10)
    )
    rows = result.scalars().all()
    tournament_log.info("tournament.leaderboard.ok", extra={"league": league, "count": len(rows)})
    return rows

# 3. Получение информации пользователя в турнире
async def get_user_tournament_info(session: AsyncSession, telegram_id: int):
    tournament_log.debug("tournament.user_info.start", extra={"telegram_id": telegram_id})
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        tournament_log.warning("tournament.user_info.not_found", extra={"telegram_id": telegram_id})
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
        tournament_log.info("tournament.user_info.no_league", extra={"telegram_id": telegram_id, "max_energy": user.max_energy})
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

    tournament_log.info(
        "tournament.user_info.ok",
        extra={"telegram_id": telegram_id, "league": league, "rank": rank, "clicks": int(user.tournament_clicks or 0)},
    )

    return {
        "league": league,
        "rank": rank,
        "clicks": user.tournament_clicks
    }

# 4. Сброс всех турнирных кликов (раз в неделю)
async def reset_tournament_data(session: AsyncSession):
    tournament_log.warning("tournament.reset.start", extra={"ts": str(datetime.utcnow())})
    result = await session.execute(
        update(User)
        .values(tournament_clicks=0, tournament_updated_at=datetime.utcnow())
    )
    # Может быть None в зависимости от драйвера, но попробуем залогировать
    affected = getattr(result, "rowcount", None)
    await session.commit()
    tournament_log.warning("tournament.reset.ok", extra={"affected": affected})

async def increment_total_spent(session: AsyncSession, amount: int):
    stats_log.info("stats.total_spent.inc.start", extra={"amount": amount})
    result = await session.execute(select(AppStats).where(AppStats.id == 1))
    stats = result.scalar_one_or_none()

    if not stats:
        stats = AppStats(id=1, total_spent=0)
        session.add(stats)
        await session.commit()  # Коммитим создание записи
        stats_log.info("stats.total_spent.created", extra={"id": 1})

    before = int(stats.total_spent or 0)
    stats.total_spent = before + amount
    await session.commit()
    stats_log.info("stats.total_spent.inc.ok", extra={"before": before, "after": int(stats.total_spent or 0)})

async def get_total_spent(session: AsyncSession) -> int:
    result = await session.execute(select(AppStats.total_spent).where(AppStats.id == 1))
    value = result.scalar()
    stats_log.debug("stats.total_spent.get", extra={"value": int(value or 0)})
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
    value = _as_naive_utc(value) or datetime.utcnow()
    if hasattr(user, "lastEnergyUpdate"):
        user.lastEnergyUpdate = value
    else:
        setattr(user, "last_energy_update", value)

# --- energy recovery ---------------------------------------------------------

def recover_energy_inplace(user: User, now_utc: datetime) -> None:
    """
    Восстановление энергии “на лету” (8 часов до полного восстановления).
    Считаем всё в naive UTC, чтобы не мешать aware/naive.
    """
    max_energy = int(user.max_energy or 100)
    if max_energy <= 0:
        max_energy = 100

    now_naive = _as_naive_utc(now_utc) or datetime.utcnow()

    last = _get_last_energy_update(user)
    if last is None:
        _set_last_energy_update(user, now_naive)
        energy_log.info("energy.recover.init_leu", extra={"user_id": user.id, "set_leu": str(now_naive)})
        return

    last_naive = _as_naive_utc(last) or datetime.utcnow()

    total_recovery_minutes = 480  # 8 часов до фула
    interval_sec = (total_recovery_minutes * 60) / max(1, max_energy)

    delta_sec = (now_naive - last_naive).total_seconds()
    if delta_sec < 1:
        return

    units = int(delta_sec // interval_sec)
    if units <= 0:
        return

    before = int(user.energy or 0)
    after  = min(max_energy, before + units)
    user.energy = after

    used_sec = units * interval_sec
    new_last = last_naive + timedelta(seconds=used_sec)

    # если дошли до максимума — обнуляем «долг» восстановления
    if before < max_energy and after == max_energy:
        _set_last_energy_update(user, now_naive)
    else:
        _set_last_energy_update(user, new_last)

    energy_log.info(
        "energy.recover.apply",
        extra={
            "user_id": user.id,
            "units": units,
            "before": before,
            "after": after,
            "max_energy": max_energy,
        },
    )

# --- clicks flush (soft-order, idempotent) -----------------------------------

async def apply_clicks_flush(
    session: AsyncSession,
    user: User,
    delta_clicks: int,
    client_seq: int,
    now_utc: Optional[datetime] = None
) -> Dict[str, int]:
    """
    Идемпотентный батч кликов с МЯГКИМ порядком.
    - Принимаем любой client_seq > last_client_seq (без требования +1).
    - Повтор/старый пакет (client_seq <= last_seq) → NOOP.
    - last_client_seq двигаем ВСЕГДА при client_seq > last_seq, даже если accepted=0,
      чтобы не застревать на «битом» пакете и не терять следующие.
    - delta_clicks трактуем как «энергия к списанию»: XP/ежедневка/турнир = accepted.
    """
    # всегда работаем в naive UTC
    now_utc = _as_naive_utc(now_utc) if now_utc else datetime.utcnow()

    # 1) Восстановим энергию
    recover_energy_inplace(user, now_utc)

    # 2) Идемпотентность + мягкий порядок
    last_seq = int(getattr(user, "last_client_seq", 0) or 0)
    cur_seq  = int(client_seq)

    requested = max(0, int(delta_clicks))
    available = max(0, int(user.energy or 0))

    base_log = {
        "user_id": user.id,
        "telegram_id": getattr(user, "telegram_id", None),
        "client_seq": cur_seq,
        "last_seq": last_seq,
        "requested": requested,
        "available": available,
        "energy": int(user.energy or 0),
        "total_xp": int(user.total_xp or 0),
        "daily_progress": int(user.daily_progress or 0),
    }
    clicks_log.info("clicks.flush.start", extra=base_log)

    if cur_seq <= last_seq:
        # повтор/старый — ничего не делаем
        clicks_log.info("clicks.noop.duplicate_or_old", extra=base_log)
        return {
            "accepted_clicks": 0,
            "energy": int(user.energy or 0),
            "total_xp": int(user.total_xp or 0),
            "daily_progress": int(user.daily_progress or 0),
            "server_seq": last_seq,
        }

    # 3) Применяем пакет (delta_clicks = «энергия к списанию»)
    accepted  = min(requested, available)
    energy_before = int(user.energy or 0)
    total_before  = int(user.total_xp or 0)
    daily_before  = int(user.daily_progress or 0)
    tourn_before  = int(getattr(user, "tournament_clicks", 0) or 0)

    if accepted > 0:
        user.energy = energy_before - accepted
        user.total_xp = total_before + accepted
        user.daily_progress = daily_before + accepted
        if hasattr(user, "tournament_clicks"):
            user.tournament_clicks = tourn_before + accepted
            setattr(user, "tournament_updated_at", now_utc)
        # фиксируем момент траты энергии (сброс таймера регена)
        _set_last_energy_update(user, now_utc)
        clicks_log.info(
            "clicks.apply",
            extra={
                **base_log,
                "accepted": accepted,
                "energy_after": int(user.energy or 0),
                "total_after": int(user.total_xp or 0),
                "daily_after": int(user.daily_progress or 0),
                "tournament_after": int(getattr(user, "tournament_clicks", 0) or 0),
            },
        )
    else:
        clicks_log.info("clicks.apply.zero", extra=base_log)

    # 4) Обновляем последовательность ВСЕГДА, раз пакет новее
    setattr(user, "last_client_seq", cur_seq)
    await session.flush()

    result = {
        "accepted_clicks": int(accepted),
        "energy": int(user.energy or 0),
        "total_xp": int(user.total_xp or 0),
        "daily_progress": int(user.daily_progress or 0),
        "server_seq": int(getattr(user, "last_client_seq", 0) or 0),
    }
    clicks_log.info("clicks.flush.done", extra={**base_log, **result})
    return result

