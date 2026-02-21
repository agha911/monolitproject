# backend/app/crud/crud_pvp.py
# CRUD для PvP Live + Challenge (асинхронный SQLAlchemy)

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Tuple
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, desc, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.pvp_models import PvpMatch, ChallengeMatch

# ✅ новая модель попыток Challenge
from app.models.pvp_challenge_attempt import PvpChallengeAttempt

from sqlalchemy import and_, or_


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

    # PvP победы (по твоей механике Live: win = +2)
    if not is_draw and winner_id is not None:
        await _add_victories(session, user_id=winner_id, delta=2)

    # best_result = max(best_result, clicks)
    await _update_best_result(session, user_id=player1_id, candidate=player1_clicks)
    await _update_best_result(session, user_id=player2_id, candidate=player2_clicks)

    await session.flush()
    return match


async def list_recent_pvp_matches(
    session: AsyncSession,
    *,
    user_id: int,
    limit: int = 20,
) -> List[PvpMatch]:
    q = (
        select(PvpMatch)
        .where(or_(PvpMatch.player1_id == user_id, PvpMatch.player2_id == user_id))
        .order_by(desc(PvpMatch.created_at))
        .limit(limit)
    )
    res = await session.execute(q)
    return list(res.scalars().all())


# ----------------------------
# Challenge (history table: ChallengeMatch)
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


# ----------------------------
# Challenge Attempts (железный лимит по START)
# ----------------------------

async def create_challenge_attempt(
    session: AsyncSession,
    *,
    challenger_id: int,
    opponent_id: int,
    opponent_best_result: int,
    ttl_minutes: int = 10,
) -> PvpChallengeAttempt:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=int(ttl_minutes))

    attempt = PvpChallengeAttempt(
        challenger_id=challenger_id,
        opponent_id=opponent_id,
        opponent_best_result=int(opponent_best_result),
        status="started",
        started_at=now,
        expires_at=expires_at,
    )
    session.add(attempt)
    await session.flush()
    return attempt


async def get_challenge_attempt_for_update(
    session: AsyncSession,
    *,
    attempt_id: int,
) -> Optional[PvpChallengeAttempt]:
    q = (
        select(PvpChallengeAttempt)
        .where(PvpChallengeAttempt.id == int(attempt_id))
        .with_for_update()
    )
    res = await session.execute(q)
    return res.scalar_one_or_none()


async def finish_challenge_attempt(
    session: AsyncSession,
    *,
    attempt: PvpChallengeAttempt,
    challenger_clicks: int,
) -> ChallengeMatch:
    """
    Завершает попытку (attempt) и пишет историю в ChallengeMatch.
    Обновления:
      - attempt.status=finished
      - attempt.challenger_clicks / is_win / finished_at
      - user victories (+1 при win)
      - user best_result = max(old, challenger_clicks)
      - запись ChallengeMatch (история)
    """
    now = datetime.now(timezone.utc)

    attempt.challenger_clicks = int(challenger_clicks)
    attempt.finished_at = now

    is_win = int(challenger_clicks) > int(attempt.opponent_best_result)
    attempt.is_win = bool(is_win)
    attempt.status = "finished"

    # история + апдейты юзера (внутри create_challenge_match)
    match = await create_challenge_match(
        session,
        challenger_id=int(attempt.challenger_id),
        opponent_id=int(attempt.opponent_id),
        challenger_clicks=int(challenger_clicks),
        opponent_best_result=int(attempt.opponent_best_result),
    )
    await session.flush()
    return match


async def expire_challenge_attempt(
    session: AsyncSession,
    *,
    attempt: PvpChallengeAttempt,
) -> None:
    if attempt.status != "started":
        return
    attempt.status = "expired"
    await session.flush()


async def count_today_challenge_attempts(
    session: AsyncSession,
    *,
    challenger_id: int,
    tz: str = "Asia/Baku",
) -> int:
    """
    ✅ Теперь считаем "попытки" по START в pvp_challenge_attempts.
    Так лимит становится железным: нажал кнопку — попытка сгорела.
    """
    q = select(func.count(PvpChallengeAttempt.id)).where(PvpChallengeAttempt.challenger_id == challenger_id)

    start_local = func.date_trunc("day", func.timezone(tz, func.now()))
    end_local = start_local + func.make_interval(0, 0, 0, 1)  # +1 day

    q = q.where(func.timezone(tz, PvpChallengeAttempt.started_at) >= start_local)
    q = q.where(func.timezone(tz, PvpChallengeAttempt.started_at) < end_local)

    res = await session.execute(q)
    return int(res.scalar_one() or 0)


# ----------------------------
# Leaderboard / Rank
# ----------------------------

async def get_pvp_leaderboard_top(
    session: AsyncSession,
    *,
    limit: int = 10,
) -> List[User]:
    q = (
        select(User)
        .order_by(desc(func.coalesce(User.pvp_victories, 0)), desc(func.coalesce(User.pvp_best_result, 0)))
        .limit(limit)
    )
    res = await session.execute(q)
    return list(res.scalars().all())


async def get_pvp_rank_for_user(session: AsyncSession, *, user_id: int) -> int:
    # Ранк по victories desc, best_result desc
    subq = (
        select(
            User.id,
            func.rank().over(
                order_by=(desc(func.coalesce(User.pvp_victories, 0)), desc(func.coalesce(User.pvp_best_result, 0)))
            ).label("rnk"),
        )
        .subquery()
    )
    q = select(subq.c.rnk).where(subq.c.id == user_id)
    res = await session.execute(q)
    r = res.scalar_one_or_none()
    return int(r or 0)


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

