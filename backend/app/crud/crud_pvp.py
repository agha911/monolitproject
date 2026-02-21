# backend/app/crud/crud_pvp.py
# CRUD для PvP Live + Challenge (асинхронный SQLAlchemy)

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Tuple

from sqlalchemy import select, desc, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.pvp_models import PvpMatch, ChallengeMatch


# ----------------------------
# DTO / helpers
# ----------------------------

@dataclass(frozen=True)
class PvpFinalizeResult:
    is_draw: bool
    winner_id: Optional[int]
    loser_id: Optional[int]
    player1_clicks: int
    player2_clicks: int
    stake: int


def _resolve_pvp_winner(
    player1_id: int,
    player2_id: int,
    player1_clicks: int,
    player2_clicks: int,
) -> Tuple[bool, Optional[int], Optional[int]]:
    """
    Возвращает (is_draw, winner_id, loser_id)
    """
    if player1_clicks == player2_clicks:
        return True, None, None

    if player1_clicks > player2_clicks:
        return False, player1_id, player2_id

    return False, player2_id, player1_id


# ----------------------------
# PvP Live
# ----------------------------

async def create_pvp_match(
    session: AsyncSession,
    *,
    player1_id: int,
    player2_id: int,
    player1_clicks: int,
    player2_clicks: int,
    stake: int,
) -> PvpMatch:
    """
    Создаёт запись pvp_matches и обновляет у пользователей:
    - pvp_victories (+2 победителю)
    - pvp_best_result (максимум кликов)
    """
    is_draw, winner_id, loser_id = _resolve_pvp_winner(
        player1_id=player1_id,
        player2_id=player2_id,
        player1_clicks=player1_clicks,
        player2_clicks=player2_clicks,
    )

    match = PvpMatch(
        player1_id=player1_id,
        player2_id=player2_id,
        player1_clicks=player1_clicks,
        player2_clicks=player2_clicks,
        stake=stake,
        is_draw=is_draw,
        winner_id=winner_id,
    )
    session.add(match)

    # Update stats (victories/best_result)
    if not is_draw and winner_id is not None:
        await _add_victories(session, user_id=winner_id, delta=2)

    # best_result для обоих игроков
    await _update_best_result(session, user_id=player1_id, candidate=player1_clicks)
    await _update_best_result(session, user_id=player2_id, candidate=player2_clicks)

    await session.flush()
    return match


async def list_recent_pvp_matches_for_user(
    session: AsyncSession,
    *,
    user_id: int,
    limit: int = 20,
    offset: int = 0,
) -> List[PvpMatch]:
    """
    История PvP матчей пользователя (последние).
    """
    q = (
        select(PvpMatch)
        .where(or_(PvpMatch.player1_id == user_id, PvpMatch.player2_id == user_id))
        .order_by(desc(PvpMatch.created_at))
        .limit(limit)
        .offset(offset)
    )
    res = await session.execute(q)
    return list(res.scalars().all())


# Compatibility aliases (used by routers/pvp.py)
async def list_recent_pvp_matches(
    session: AsyncSession,
    *,
    user_id: int,
    limit: int = 20,
) -> List[PvpMatch]:
    """
    Backward-compatible name expected by routers.
    """
    return await list_recent_pvp_matches_for_user(session, user_id=user_id, limit=limit, offset=0)


async def get_pvp_match_by_id(session: AsyncSession, match_id: int) -> Optional[PvpMatch]:
    q = select(PvpMatch).where(PvpMatch.id == match_id)
    res = await session.execute(q)
    return res.scalar_one_or_none()


# ----------------------------
# Challenge
# ----------------------------

async def create_challenge_match(
    session: AsyncSession,
    *,
    challenger_id: int,
    opponent_id: int,
    challenger_clicks: int,
    opponent_best_result: int,
) -> ChallengeMatch:
    """
    Создаёт запись challenge_matches и обновляет у challenger:
    - pvp_victories (+1 при победе)
    - pvp_best_result (кандидат = challenger_clicks)
    """
    is_win = challenger_clicks > opponent_best_result

    match = ChallengeMatch(
        challenger_id=challenger_id,
        opponent_id=opponent_id,
        challenger_clicks=challenger_clicks,
        opponent_best_result=opponent_best_result,
        is_win=is_win,
    )
    session.add(match)

    if is_win:
        await _add_victories(session, user_id=challenger_id, delta=1)

    await _update_best_result(session, user_id=challenger_id, candidate=challenger_clicks)

    await session.flush()
    return match


async def list_recent_challenge_matches_for_user(
    session: AsyncSession,
    *,
    user_id: int,
    limit: int = 20,
    offset: int = 0,
) -> List[ChallengeMatch]:
    """
    История Challenge матчей пользователя (как challenger или opponent).
    """
    q = (
        select(ChallengeMatch)
        .where(or_(ChallengeMatch.challenger_id == user_id, ChallengeMatch.opponent_id == user_id))
        .order_by(desc(ChallengeMatch.created_at))
        .limit(limit)
        .offset(offset)
    )
    res = await session.execute(q)
    return list(res.scalars().all())


async def list_recent_challenge_matches(
    session: AsyncSession,
    *,
    challenger_id: int,
    limit: int = 20,
) -> List[ChallengeMatch]:
    """
    Backward-compatible helper expected by routers: returns matches where the user is challenger.
    """
    q = (
        select(ChallengeMatch)
        .where(ChallengeMatch.challenger_id == challenger_id)
        .order_by(desc(ChallengeMatch.created_at))
        .limit(limit)
    )
    res = await session.execute(q)
    return list(res.scalars().all())


async def count_today_challenge_attempts(
    session: AsyncSession,
    *,
    challenger_id: int,
    tz: str = "Asia/Baku",
) -> int:
    """
    Считает количество запусков Challenge за "сегодня" для challenger_id.
    Важно: tz оставлен как было (если у тебя использовался elsewhere).
    """
    # Берём границы суток в UTC, используя timezone в Postgres.
    # Упрощённо: считаем в tz через now() AT TIME ZONE.
    # Если захочешь строго по AZ (UTC+4) — у тебя это уже есть в helpers.
    q = select(func.count(ChallengeMatch.id)).where(ChallengeMatch.challenger_id == challenger_id)

    # Ограничение по дню: created_at >= start_of_day && < next_day
    # Используем timezone(tz, now()) чтобы получить локальный "сейчас", затем date_trunc('day', ...)
    start_local = func.date_trunc("day", func.timezone(tz, func.now()))
    end_local = start_local + func.make_interval(0, 0, 0, 1)  # +1 day

    q = q.where(func.timezone(tz, ChallengeMatch.created_at) >= start_local)
    q = q.where(func.timezone(tz, ChallengeMatch.created_at) < end_local)

    res = await session.execute(q)
    return int(res.scalar_one() or 0)


# ----------------------------
# Leaderboard / Rank
# ----------------------------

async def get_pvp_leaderboard_top(session: AsyncSession, *, limit: int = 10) -> List[User]:
    """
    ТОП по pvp_victories, затем best_result.
    """
    q = (
        select(User)
        .order_by(desc(func.coalesce(User.pvp_victories, 0)), desc(func.coalesce(User.pvp_best_result, 0)))
        .limit(limit)
    )
    res = await session.execute(q)
    return list(res.scalars().all())


async def get_pvp_rank_for_user(session: AsyncSession, *, user_id: int) -> Optional[int]:
    """
    Ранг пользователя среди всех по pvp_victories, затем best_result.
    Возвращает 1..N или None если user не найден.
    """
    # Подтверждаем что user есть
    u = (await session.execute(select(User.id).where(User.id == user_id))).scalar_one_or_none()
    if not u:
        return None

    # Ранг = 1 + количество пользователей, у которых (victories, best) строго больше
    me_q = select(
        func.coalesce(User.pvp_victories, 0),
        func.coalesce(User.pvp_best_result, 0),
    ).where(User.id == user_id)
    me_row = (await session.execute(me_q)).first()
    if not me_row:
        return None

    my_v, my_best = int(me_row[0] or 0), int(me_row[1] or 0)

    better_q = select(func.count(User.id)).where(
        or_(
            func.coalesce(User.pvp_victories, 0) > my_v,
            and_(
                func.coalesce(User.pvp_victories, 0) == my_v,
                func.coalesce(User.pvp_best_result, 0) > my_best,
            ),
        )
    )

    better = int((await session.execute(better_q)).scalar_one() or 0)
    return better + 1


# ----------------------------
# Weekly reset
# ----------------------------

async def reset_weekly_pvp_victories_for_all(session: AsyncSession) -> int:
    """
    Сбрасывает pvp_victories у всех пользователей.
    Возвращает количество затронутых строк.
    """
    res = await session.execute(
        User.__table__.update().values(pvp_victories=0)  # type: ignore
    )
    await session.flush()
    return int(getattr(res, "rowcount", 0) or 0)


# ----------------------------
# Internal update helpers
# ----------------------------

async def _add_victories(session: AsyncSession, *, user_id: int, delta: int) -> None:
    await session.execute(
        User.__table__
        .update()
        .where(User.id == user_id)
        .values(pvp_victories=func.coalesce(User.pvp_victories, 0) + int(delta))  # type: ignore
    )


async def _update_best_result(session: AsyncSession, *, user_id: int, candidate: int) -> None:
    # best = max(best, candidate)
    await session.execute(
        User.__table__
        .update()
        .where(User.id == user_id)
        .values(pvp_best_result=func.greatest(func.coalesce(User.pvp_best_result, 0), int(candidate)))  # type: ignore
    )

