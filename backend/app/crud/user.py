import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update  # для reset_tournament_data
from typing import Optional, Dict, Union
from datetime import datetime, timedelta, timezone
from app.models.user import User
from app.models.app_stats import AppStats
from sqlalchemy.orm.attributes import flag_modified
from math import ceil

# ------- простые хелперы логирования (без extra) -------
def _kv(d: dict) -> str:
    return " ".join(f"{k}={v}" for k, v in d.items())

def _log(logger: logging.Logger, level: str, event: str, **fields):
    line = f"{event}"
    if fields:
        line += " | " + _kv(fields)
    if level == "debug":
        logger.debug(line)
    elif level == "warning":
        logger.warning(line)
    elif level == "error":
        logger.error(line)
    else:
        logger.info(line)

clicks_log = logging.getLogger("app.clicks")
energy_log = logging.getLogger("app.energy")
tournament_log = logging.getLogger("app.tournament")
daily_log = logging.getLogger("app.daily")
users_log = logging.getLogger("app.users")
stats_log = logging.getLogger("app.stats")

# --- безопасное получение пользователя ---
async def get_user_for_update(session: AsyncSession, user_id: int) -> User:
    _log(users_log, "debug", "users.get_user_for_update.start", user_id=user_id)
    result = await session.execute(
        select(User).where(User.id == user_id).with_for_update()
    )
    user = result.scalar_one()
    _log(users_log, "info", "users.get_user_for_update.ok", user_id=user_id)
    return user

async def get_user(session: AsyncSession, telegram_id: int):
    _log(users_log, "debug", "users.get_user.start", telegram_id=telegram_id)
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    _log(users_log, "info", f"users.get_user.{ 'found' if user else 'none' }",
         telegram_id=telegram_id, found=bool(user))
    return user

async def create_user(
    session: AsyncSession,
    user_id: int,
    username: str,
    first_name: str,
    last_name: str,
    invited_by: Optional[int] = None
) -> User:
    _log(users_log, "info", "users.create_user.start",
         user_id=user_id, username=username, invited_by=invited_by)
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
    _log(users_log, "info", "users.create_user.ok", user_id=user_id)
    return user

async def update_progress(
    session: AsyncSession,
    telegram_id: int,
    energy: int,
    total_xp: int
):
    _log(users_log, "info", "users.update_progress.start",
         telegram_id=telegram_id, energy=energy, total_xp=total_xp)
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if user:
        before_energy = int(user.energy or 0)
        before_xp = int(user.total_xp or 0)
        user.energy = energy
        user.total_xp = total_xp
        await session.commit()
        await session.refresh(user)
        _log(users_log, "info", "users.update_progress.ok",
             telegram_id=telegram_id,
             energy_before=before_energy, energy_after=energy,
             xp_before=before_xp, xp_after=total_xp)
    else:
        _log(users_log, "warning", "users.update_progress.not_found", telegram_id=telegram_id)

async def update_energy_and_time(
    session: AsyncSession,
    telegram_id: int,
    energy: int,
    time: datetime
):
    # нормализуем к naive UTC
    def _as_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt
        return dt.astimezone(timezone.utc).replace(tzinfo=None)

    time = _as_naive_utc(time)
    _log(users_log, "info", "users.update_energy_and_time.start",
         telegram_id=telegram_id, energy=energy, time=str(time))
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
        _log(users_log, "info", "users.update_energy_and_time.ok",
             telegram_id=telegram_id,
             energy_before=before_energy, energy_after=energy,
             leu_before=str(before_leu), leu_after=str(time))
    else:
        _log(users_log, "warning", "users.update_energy_and_time.not_found", telegram_id=telegram_id)

async def get_leaderboard(session: AsyncSession, limit: int = 50):
    _log(users_log, "debug", "users.get_leaderboard.start", limit=limit)
    result = await session.execute(
        select(User).order_by(User.total_xp.desc()).limit(limit)
    )
    rows = result.scalars().all()
    _log(users_log, "info", "users.get_leaderboard.ok", limit=limit, count=len(rows))
    return rows

async def complete_task(session: AsyncSession, user: User, task_id: str, reward: int = 50):
    _log(daily_log, "info", "daily.complete_task.start", user_id=user.id, task_id=task_id)
    if task_id in user.completed_tasks:
        _log(daily_log, "info", "daily.complete_task.already_done", user_id=user.id, task_id=task_id)
        return False
    before = int(user.total_xp or 0)
    user.completed_tasks.append(task_id)
    flag_modified(user, "completed_tasks")
    user.total_xp = before + reward
    await session.commit()
    await session.refresh(user)
    _log(daily_log, "info", "daily.complete_task.ok",
         user_id=user.id, task_id=task_id, reward=reward, xp_before=before, xp_after=int(user.total_xp or 0))
    return True

async def daily_checkin(session: AsyncSession, user: User, now: datetime, reward: int, streak: int):
    _log(daily_log, "info", "daily.checkin.start", user_id=user.id, streak=streak, reward=reward)
    before = int(user.total_xp or 0)
    user.last_checkin = now
    user.daily_streak = streak
    user.total_xp = before + reward
    await session.commit()
    await session.refresh(user)
    _log(daily_log, "info", "daily.checkin.ok", user_id=user.id, xp_before=before, xp_after=int(user.total_xp or 0))
    return user

async def mark_joined_group(session: AsyncSession, user: User, reward: int = 50):
    _log(daily_log, "info", "daily.joined_group.start", user_id=user.id)
    if user.joined_group:
        _log(daily_log, "info", "daily.joined_group.already", user_id=user.id)
        return False
    before = int(user.total_xp or 0)
    user.joined_group = True
    user.total_xp = before + reward
    await session.commit()
    await session.refresh(user)
    _log(daily_log, "info", "daily.joined_group.ok",
         user_id=user.id, xp_before=before, xp_after=int(user.total_xp or 0))
    return True

async def assign_or_get_daily_task(session: AsyncSession, user: User):
    now = datetime.utcnow()
    today = now.date()

    if user.daily_updated_at and user.daily_updated_at.date() == today:
        _log(daily_log, "info", "daily.assign_or_get.reuse",
             user_id=user.id, target=user.daily_target,
             progress=user.daily_progress, completed=user.daily_completed)
        return {
            "daily_target": user.daily_target,
            "daily_progress": user.daily_progress,
            "daily_completed": user.daily_completed,
        }

    min_energy = 100
    max_energy = 30000
    max_coeff = 3.5
    min_coeff = 1.2

    energy = user.max_energy or 100
    ratio = (energy - min_energy) / (max_energy - min_energy)
    coefficient = max_coeff - ratio * (max_coeff - min_coeff)
    target = ceil(energy * coefficient)

    before_t = user.daily_target
    before_p = user.daily_progress
    user.daily_target = target
    user.daily_progress = 0
    user.daily_completed = False
    user.daily_reward_claimed = False
    user.daily_updated_at = now

    await session.commit()
    await session.refresh(user)

    _log(daily_log, "info", "daily.assign_or_get.new",
         user_id=user.id, max_energy=energy, coefficient=coefficient,
         target=target, before_target=before_t, before_progress=before_p)

    return {
        "daily_target": target,
        "daily_progress": 0,
        "daily_completed": False,
    }

async def increment_tournament_clicks(session: AsyncSession, telegram_id: int, amount: int):
    _log(tournament_log, "info", "tournament.increment_clicks.start", telegram_id=telegram_id, amount=amount)
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()

    if user:
        before = int(user.tournament_clicks or 0)
        user.tournament_clicks = before + amount
        user.tournament_updated_at = datetime.utcnow()
        session.add(user)
        await session.commit()
        _log(tournament_log, "info", "tournament.increment_clicks.ok",
             telegram_id=telegram_id, before=before, after=int(user.tournament_clicks or 0))
    else:
        _log(tournament_log, "warning", "tournament.increment_clicks.not_found", telegram_id=telegram_id)

async def get_tournament_leaderboard(session: AsyncSession, league: str):
    if league == "bronze":
        min_energy, max_energy = 5000, 14999
    elif league == "silver":
        min_energy, max_energy = 15000, 24999
    elif league == "gold":
        min_energy, max_energy = 25000, 30000
    else:
        _log(tournament_log, "error", "tournament.leaderboard.invalid_league", league=league)
        raise ValueError("Invalid league")

    _log(tournament_log, "debug", "tournament.leaderboard.start", league=league, min=min_energy, max=max_energy)
    result = await session.execute(
        select(User)
        .where(User.max_energy >= min_energy, User.max_energy <= max_energy)
        .order_by(User.tournament_clicks.desc())
        .limit(10)
    )
    rows = result.scalars().all()
    _log(tournament_log, "info", "tournament.leaderboard.ok", league=league, count=len(rows))
    return rows

async def get_user_tournament_info(session: AsyncSession, telegram_id: int):
    _log(tournament_log, "debug", "tournament.user_info.start", telegram_id=telegram_id)
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        _log(tournament_log, "warning", "tournament.user_info.not_found", telegram_id=telegram_id)
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
        _log(tournament_log, "info", "tournament.user_info.no_league", telegram_id=telegram_id, max_energy=user.max_energy)
        return {"league": None, "rank": None, "clicks": 0}

    result = await session.execute(
        select(User)
        .where(User.max_energy >= min_e, User.max_energy < max_e)
        .order_by(User.tournament_clicks.desc())
    )
    users = result.scalars().all()
    rank = next((i + 1 for i, u in enumerate(users) if u.telegram_id == telegram_id), None)

    _log(tournament_log, "info", "tournament.user_info.ok",
         telegram_id=telegram_id, league=league, rank=rank, clicks=int(user.tournament_clicks or 0))

    return {"league": league, "rank": rank, "clicks": user.tournament_clicks}

async def reset_tournament_data(session: AsyncSession):
    _log(tournament_log, "warning", "tournament.reset.start", ts=str(datetime.utcnow()))
    result = await session.execute(
        update(User).values(tournament_clicks=0, tournament_updated_at=datetime.utcnow())
    )
    affected = getattr(result, "rowcount", None)
    await session.commit()
    _log(tournament_log, "warning", "tournament.reset.ok", affected=affected)

async def increment_total_spent(session: AsyncSession, amount: int):
    _log(stats_log, "info", "stats.total_spent.inc.start", amount=amount)

    result = await session.execute(select(AppStats).where(AppStats.id == 1))
    stats = result.scalar_one_or_none()

    if not stats:
        stats = AppStats(id=1, total_spent=0)
        session.add(stats)
        # важно: flush вместо commit
        await session.flush()
        _log(stats_log, "info", "stats.total_spent.created", id=1)

    before = int(stats.total_spent or 0)
    stats.total_spent = before + amount

    # commit здесь НЕ делаем — он должен быть в вызывающей бизнес-операции
    _log(
        stats_log,
        "info",
        "stats.total_spent.inc.ok",
        before=before,
        after=int(stats.total_spent or 0),
    )

async def get_total_spent(session: AsyncSession) -> int:
    result = await session.execute(select(AppStats.total_spent).where(AppStats.id == 1))
    value = result.scalar()
    _log(stats_log, "debug", "stats.total_spent.get", value=int(value or 0))
    return value or 0

# =========================
# ЛОГИКА ДЛЯ БАТЧ-КЛИКОВ
# =========================

def _as_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)

def _get_last_energy_update(user: User) -> Optional[datetime]:
    if hasattr(user, "lastEnergyUpdate"):
        return user.lastEnergyUpdate
    return getattr(user, "last_energy_update", None)

def _set_last_energy_update(user: User, value: datetime) -> None:
    value = _as_naive_utc(value) or datetime.utcnow()
    if hasattr(user, "lastEnergyUpdate"):
        user.lastEnergyUpdate = value
    else:
        setattr(user, "last_energy_update", value)

def recover_energy_inplace(user: User, now_utc: datetime) -> None:
    max_energy = int(user.max_energy or 100)
    if max_energy <= 0:
        max_energy = 100

    now_naive = _as_naive_utc(now_utc) or datetime.utcnow()

    last = _get_last_energy_update(user)
    if last is None:
        _set_last_energy_update(user, now_naive)
        _log(energy_log, "info", "energy.recover.init_leu", user_id=user.id, set_leu=str(now_naive))
        return

    last_naive = _as_naive_utc(last) or datetime.utcnow()

    total_recovery_minutes = 480  # 8 часов
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

    if before < max_energy and after == max_energy:
        _set_last_energy_update(user, now_naive)
    else:
        _set_last_energy_update(user, new_last)

    _log(energy_log, "info", "energy.recover.apply",
         user_id=user.id, units=units, before=before, after=after, max_energy=max_energy)

async def apply_clicks_flush(
    session: AsyncSession,
    user: User,
    delta_clicks: int,
    client_seq: int,
    now_utc: Optional[datetime] = None
) -> Dict[str, Union[int, str]]:
    """
    Мягкий порядок + идемпотентность:
    - принимаем любой client_seq > last_client_seq;
    - дубликаты/старые (<=) — NOOP;
    - новее — двигаем seq даже если accepted=0.
    """
    now_utc = _as_naive_utc(now_utc) if now_utc else datetime.utcnow()
    recover_energy_inplace(user, now_utc)

    last_seq = int(getattr(user, "last_client_seq", 0) or 0)
    cur_seq  = int(client_seq)

    requested = max(0, int(delta_clicks))
    available = max(0, int(user.energy or 0))

    base = dict(
        user_id=user.id,
        telegram_id=getattr(user, "telegram_id", None),
        client_seq=cur_seq,
        last_seq=last_seq,
        requested=requested,
        available=available,
        energy=int(user.energy or 0),
        total_xp=int(user.total_xp or 0),
        daily_progress=int(user.daily_progress or 0),
    )
    _log(clicks_log, "info", "clicks.flush.start", **base)

    # дубликат/старый пакет — ничего не меняем
    if cur_seq <= last_seq:
        expected_next = last_seq + 1
        _log(clicks_log, "info", "clicks.noop.duplicate_or_old", **base, expected_next_seq=expected_next)
        return {
            "accepted_clicks": 0,
            "energy": int(user.energy or 0),
            "total_xp": int(user.total_xp or 0),
            "daily_progress": int(user.daily_progress or 0),
            "server_seq": last_seq,
            "reason": "duplicate_or_old",
            "expected_next_seq": expected_next,
        }

    accepted = min(requested, available)
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
        _set_last_energy_update(user, now_utc)

        _log(clicks_log, "info", "clicks.apply",
             **base,
             accepted=accepted,
             energy_after=int(user.energy or 0),
             total_after=int(user.total_xp or 0),
             daily_after=int(user.daily_progress or 0),
             tournament_after=int(getattr(user, "tournament_clicks", 0) or 0))
        reason = "ok"
    else:
        _log(clicks_log, "info", "clicks.apply.zero", **base)
        reason = "no_energy"

    # продвинем последовательность
    setattr(user, "last_client_seq", cur_seq)
    await session.flush()

    server_seq = int(getattr(user, "last_client_seq", 0) or 0)
    result = {
        "accepted_clicks": int(accepted),
        "energy": int(user.energy or 0),
        "total_xp": int(user.total_xp or 0),
        "daily_progress": int(user.daily_progress or 0),
        "server_seq": server_seq,
        "reason": reason,
        "expected_next_seq": server_seq + 1,
    }
    _log(clicks_log, "info", "clicks.flush.done", **{**base, **result})
    return result

