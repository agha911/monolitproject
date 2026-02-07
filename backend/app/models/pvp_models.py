# backend/app/services/pvp_service.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User
from app.models.pvp_models import PvpSession

from app.crud.crud_pvp import (
    create_pvp_match,
    create_challenge_match,
    count_today_challenge_attempts,
)

from app.helpers.pvp_helpers import (
    resolve_pvp_outcome,
    calc_pvp_payout,
    resolve_challenge_outcome,
)


@dataclass(frozen=True)
class LivePvpResult:
    match_id: int
    is_draw: bool
    winner_id: Optional[int]
    player1_id: int
    player2_id: int
    player1_clicks: int
    player2_clicks: int
    stake: int
    player1_coins_delta: int
    player2_coins_delta: int
    player1_total_xp: int
    player2_total_xp: int


@dataclass(frozen=True)
class ChallengeResult:
    match_id: int
    challenger_id: int
    opponent_id: int
    challenger_clicks: int
    opponent_best_result: int
    is_win: bool
    victories_delta: int
    challenger_total_xp: int
    challenger_best_result: int


class PvpError(Exception):
    code: str = "pvp_error"


class UserNotFound(PvpError):
    code = "pvp_user_not_found"


class InsufficientCoins(PvpError):
    code = "pvp_insufficient_coins"


class ChallengeLimitExceeded(PvpError):
    code = "challenge_limit_exceeded"


class InvalidPayload(PvpError):
    code = "pvp_invalid_payload"


class SessionNotFound(PvpError):
    code = "pvp_session_not_found"


class SessionNotActive(PvpError):
    code = "pvp_session_not_active"


class SessionExpired(PvpError):
    code = "pvp_session_expired"


async def _get_user_for_update(session: AsyncSession, user_id: int) -> User:
    q = select(User).where(User.id == user_id).with_for_update()
    res = await session.execute(q)
    user = res.scalar_one_or_none()
    if not user:
        raise UserNotFound(f"User not found: {user_id}")
    return user


async def _get_session_for_update(session: AsyncSession, match_token: str) -> PvpSession:
    q = (
        select(PvpSession)
        .where(PvpSession.match_token == match_token)
        .with_for_update()
        .limit(1)
    )
    res = await session.execute(q)
    s = res.scalar_one_or_none()
    if not s:
        raise SessionNotFound("Session not found")
    return s


def _calc_coin_deltas_from_stored(winner_id: Optional[int], is_draw: bool, p1_id: int, p2_id: int, stake: int) -> tuple[int, int]:
    # PvP Live: win = +stake / -stake, draw = 0/0
    if is_draw or winner_id is None:
        return 0, 0
    if winner_id == p1_id:
        return stake, -stake
    if winner_id == p2_id:
        return -stake, stake
    # fallback
    return 0, 0


async def finish_live_pvp(
    session: AsyncSession,
    *,
    player1_id: int,
    player2_id: int,
    player1_clicks: int,
    player2_clicks: int,
    stake: int = 50000,
) -> LivePvpResult:
    if player1_id == player2_id:
        raise InvalidPayload("player1_id and player2_id must be different")
    if player1_clicks < 0 or player2_clicks < 0:
        raise InvalidPayload("clicks must be >= 0")
    if stake < 0:
        raise InvalidPayload("stake must be >= 0")

    first_id, second_id = (player1_id, player2_id) if player1_id < player2_id else (player2_id, player1_id)

    u_first = await _get_user_for_update(session, first_id)
    u_second = await _get_user_for_update(session, second_id)

    if u_first.id == player1_id:
        u1, u2 = u_first, u_second
    else:
        u1, u2 = u_second, u_first

    if stake > 0:
        if u1.total_xp < stake:
            raise InsufficientCoins(f"Player1 has not enough coins (total_xp). need={stake}, has={u1.total_xp}")
        if u2.total_xp < stake:
            raise InsufficientCoins(f"Player2 has not enough coins (total_xp). need={stake}, has={u2.total_xp}")

    outcome = resolve_pvp_outcome(
        player1_id=player1_id,
        player2_id=player2_id,
        player1_clicks=player1_clicks,
        player2_clicks=player2_clicks,
    )
    payout = calc_pvp_payout(
        player1_id=player1_id,
        player2_id=player2_id,
        outcome=outcome,
        stake=stake,
    )

    if stake > 0:
        u1.total_xp -= stake
        u2.total_xp -= stake

    if outcome.is_draw:
        if stake > 0:
            u1.total_xp += stake
            u2.total_xp += stake
    else:
        if payout.player1_delta > 0:
            u1.total_xp += (2 * stake)
        else:
            u2.total_xp += (2 * stake)

    match = await create_pvp_match(
        session,
        player1_id=player1_id,
        player2_id=player2_id,
        player1_clicks=player1_clicks,
        player2_clicks=player2_clicks,
        stake=stake,
    )

    await session.flush()

    return LivePvpResult(
        match_id=match.id,
        is_draw=outcome.is_draw,
        winner_id=outcome.winner_id,
        player1_id=player1_id,
        player2_id=player2_id,
        player1_clicks=player1_clicks,
        player2_clicks=player2_clicks,
        stake=stake,
        player1_coins_delta=payout.player1_delta,
        player2_coins_delta=payout.player2_delta,
        player1_total_xp=u1.total_xp,
        player2_total_xp=u2.total_xp,
    )


async def finish_live_pvp_session(
    session: AsyncSession,
    *,
    match_token: str,
    requester_user_id: int,
    opponent_user_id: int,
    requester_clicks: int,
    opponent_clicks: int,
    stake_fixed: int = 50000,
) -> LivePvpResult:
    """
    Безопасная финализация:
    - ищем session по match_token FOR UPDATE
    - проверяем status/expire
    - проверяем участников
    - если уже finished -> idempotent ответ без повторного списания
    - иначе вызываем finish_live_pvp и фиксируем поля сессии
    """
    if requester_user_id == opponent_user_id:
        raise InvalidPayload("requester_user_id and opponent_user_id must be different")
    if requester_clicks < 0 or opponent_clicks < 0:
        raise InvalidPayload("clicks must be >= 0")

    s = await _get_session_for_update(session, match_token)

    # expire check
    now = datetime.now(timezone.utc)
    if s.expires_at is not None and s.expires_at < now:
        if s.status == "active":
            s.status = "expired"
            await session.flush()
        raise SessionExpired("Session expired")

    if s.status != "active":
        # idempotent path if finished
        if s.status == "finished" and s.pvp_match_id is not None:
            # вернём сохранённые clicks/outcome, а балансы — текущие
            u1 = await _get_user_for_update(session, s.player1_id)
            u2 = await _get_user_for_update(session, s.player2_id)
            p1_delta, p2_delta = _calc_coin_deltas_from_stored(
                winner_id=s.winner_id,
                is_draw=bool(s.is_draw),
                p1_id=s.player1_id,
                p2_id=s.player2_id,
                stake=int(s.stake or stake_fixed),
            )
            return LivePvpResult(
                match_id=int(s.pvp_match_id),
                is_draw=bool(s.is_draw),
                winner_id=int(s.winner_id) if s.winner_id is not None else None,
                player1_id=int(s.player1_id),
                player2_id=int(s.player2_id),
                player1_clicks=int(s.player1_clicks or 0),
                player2_clicks=int(s.player2_clicks or 0),
                stake=int(s.stake or stake_fixed),
                player1_coins_delta=p1_delta,
                player2_coins_delta=p2_delta,
                player1_total_xp=int(u1.total_xp or 0),
                player2_total_xp=int(u2.total_xp or 0),
            )
        raise SessionNotActive(f"Session is not active: {s.status}")

    # validate participants (оба допустимые пары)
    allowed = {s.player1_id, s.player2_id}
    if requester_user_id not in allowed or opponent_user_id not in allowed:
        raise InvalidPayload("Players do not match this session")
    if requester_user_id == opponent_user_id:
        raise InvalidPayload("Invalid participants")

    # нормализуем player1/player2 под сессию
    if requester_user_id == s.player1_id:
        p1_clicks = requester_clicks
        p2_clicks = opponent_clicks
    else:
        # requester = player2
        p1_clicks = opponent_clicks
        p2_clicks = requester_clicks

    # stake фиксированный
    stake = stake_fixed

    result = await finish_live_pvp(
        session,
        player1_id=s.player1_id,
        player2_id=s.player2_id,
        player1_clicks=p1_clicks,
        player2_clicks=p2_clicks,
        stake=stake,
    )

    s.status = "finished"
    s.finished_at = now
    s.pvp_match_id = result.match_id
    s.winner_id = result.winner_id
    s.is_draw = bool(result.is_draw)
    s.stake = stake
    s.player1_clicks = p1_clicks
    s.player2_clicks = p2_clicks

    await session.flush()
    return result


async def run_challenge(
    session: AsyncSession,
    *,
    challenger_id: int,
    opponent_id: int,
    challenger_clicks: int,
    daily_limit: int = 5,
) -> ChallengeResult:
    if challenger_id == opponent_id:
        raise InvalidPayload("challenger_id and opponent_id must be different")
    if challenger_clicks < 0:
        raise InvalidPayload("challenger_clicks must be >= 0")

    challenger = await _get_user_for_update(session, challenger_id)
    opponent = await _get_user_for_update(session, opponent_id)

    attempts_today = await count_today_challenge_attempts(session, challenger_id=challenger_id)
    if attempts_today >= daily_limit:
        raise ChallengeLimitExceeded(f"Daily challenge limit exceeded: {attempts_today}/{daily_limit}")

    opponent_best = int(opponent.pvp_best_result or 0)

    outcome = resolve_challenge_outcome(
        challenger_clicks=challenger_clicks,
        opponent_best_result=opponent_best,
    )

    match = await create_challenge_match(
        session,
        challenger_id=challenger_id,
        opponent_id=opponent_id,
        challenger_clicks=challenger_clicks,
        opponent_best_result=opponent_best,
    )

    await session.flush()

    return ChallengeResult(
        match_id=match.id,
        challenger_id=challenger_id,
        opponent_id=opponent_id,
        challenger_clicks=challenger_clicks,
        opponent_best_result=opponent_best,
        is_win=bool(outcome.is_win),
        victories_delta=1 if outcome.is_win else 0,
        challenger_total_xp=int(challenger.total_xp or 0),
        challenger_best_result=int(challenger.pvp_best_result or 0),
    )
