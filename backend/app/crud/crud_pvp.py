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


def _resolve_pvp_winner(player1_id: int, player2_id: int, player1_clicks: int, player2_clicks: int) -> Tuple[bool, Optional[int], Optional[int]]:
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
    stake: int = 50000,
) -> PvpMatch:
    """
    Создаёт запись PvP-матча (история). Тут же фиксируем победителя/ничью.
    Награды/списания монет — отдельной логикой (обычно в сервисе), но
    победы и best_result можно обновлять тут.
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
        winner_id=winner_id,
        is_draw=is_draw,
    )

    session.add(match)

    # Обновление best_result обоих игроков (постоянный рекорд)
    await _update_best_result(session, user_id=player1_id, new_result=player1_clicks)
    await _update_best_result(session, user_id=player2_id, new_result=player2_clicks)

    # Победы: PvP Live = +2 победы победителю, ничья = 0
    if not is_draw and winner_id is not None:
        await _add_victories(session, user_id=winner_id, delta=2)

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
    Создаёт запись Challenge-матча и, если победа, начисляет +1 победу.
    best_result челленджера обновляем по факту кликов (постоянный рекорд).
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

    # best_result челленджера — постоянный рекорд
    await _update_best_result(session, user_id=challenger_id, new_result=challenger_clicks)

    # Победы: Challenge = +1 победа только при win
    if is_win:
        await _add_victories(session, user_id=challenger_id, delta=1)

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


async def count_today_challenge_attempts(
    session: AsyncSession,
    *,
    challenger_id: int,
    tz: str = "Asia/Baku",
) -> int:
    """
    Считает количество Challenge запусков за "сегодня" (по Баку).
    Лимит 5/день — проверяй этим методом в сервисе/эндпоинте.

    Реализация через date_trunc с таймзоной на стороне Postgres.
    """
    # created_at у нас timestamptz, поэтому считаем границы дня в TZ
    # start_of_day = date_trunc('day', now() at time zone 'Asia/Baku') interpreted as timestamp without tz,
    # then back to timestamptz via timezone().
    start_of_day = func.timezone(
        tz,
        func.date_trunc("day", func.timezone(tz, func.now()))
    )
    # end = start + 1 day
    end_of_day = start_of_day + func.make_interval(days=1)

    q = (
        select(func.count(ChallengeMatch.id))
        .where(ChallengeMatch.challenger_id == challenger_id)
        .where(ChallengeMatch.created_at >= start_of_day)
        .where(ChallengeMatch.created_at < end_of_day)
    )
    res = await session.execute(q)
    return int(res.scalar_one() or 0)


# ----------------------------
# Leaderboard / рейтинги
# ----------------------------

async def get_pvp_leaderboard_top(
    session: AsyncSession,
    *,
    limit: int = 50,
) -> List[User]:
    """
    Топ пользователей по pvp_victories (weekly).
    """
    q = (
        select(User)
        .order_by(desc(User.pvp_victories), desc(User.pvp_best_result), desc(User.total_xp), User.id.asc())
        .limit(limit)
    )
    res = await session.execute(q)
    return list(res.scalars().all())


async def get_pvp_rank_for_user(session: AsyncSession, *, user_id: int) -> Optional[int]:
    """
    Возвращает место пользователя в общем рейтинге (1..N) по pvp_victories.
    Делает ранжирование на стороне БД (window function).
    """
    ranked = (
        select(
            User.id.label("user_id"),
            func.rank().over(
                order_by=(desc(User.pvp_victories), desc(User.pvp_best_result), desc(User.total_xp), User.id.asc())
            ).label("rnk"),
        )
        .subquery()
    )

    q = select(ranked.c.rnk).where(ranked.c.user_id == user_id)
    res = await session.execute(q)
    rnk = res.scalar_one_or_none()
    return int(rnk) if rnk is not None else None


# ----------------------------
# Weekly reset (victories only)
# ----------------------------

async def reset_weekly_pvp_victories_for_all(session: AsyncSession) -> int:
    """
    Сбрасывает pvp_victories у всех пользователей.
    Возвращает количество затронутых строк.
    """
    from sqlalchemy import update

    q = update(User).values(pvp_victories=0)
    res = await session.execute(q)
    # res.rowcount может быть None в некоторых драйверах; возвращаем 0 если так
    return int(res.rowcount or 0)


# ----------------------------
# Internal user updates
# ----------------------------

async def _add_victories(session: AsyncSession, *, user_id: int, delta: int) -> None:
    """
    pvp_victories += delta
    """
    from sqlalchemy import update

    q = (
        update(User)
        .where(User.id == user_id)
        .values(pvp_victories=User.pvp_victories + delta)
    )
    await session.execute(q)


async def _update_best_result(session: AsyncSession, *, user_id: int, new_result: int) -> None:
    """
    pvp_best_result = max(pvp_best_result, new_result)
    """
    from sqlalchemy import update, case

    q = (
        update(User)
        .where(User.id == user_id)
        .values(
            pvp_best_result=case(
                (User.pvp_best_result < new_result, new_result),
                else_=User.pvp_best_result,
            )
        )
    )
    await session.execute(q)
