# backend/app/services/pvp_service.py
# Сервис-логика поверх CRUD: атомарные изменения total_xp (монеты), победы/рекорды, лимиты Challenge.

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from datetime import datetime, timezone

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


# ----------------------------
# DTO
# ----------------------------

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
    # Дельты по монетам (total_xp)
    player1_coins_delta: int
    player2_coins_delta: int
    # Итоговые балансы (после операции)
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


# ----------------------------
# Exceptions (чтобы роутер красиво отрабатывал)
# ----------------------------

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


# ✅ R0/R1 session errors (роутер их импортирует)
class SessionNotFound(PvpError):
    code = "pvp_session_not_found"


class SessionNotActive(PvpError):
    code = "pvp_session_not_active"


class SessionExpired(PvpError):
    code = "pvp_session_expired"


# ----------------------------
# Internal helpers
# ----------------------------

async def _get_user_for_update(session: AsyncSession, user_id: int) -> User:
    """
    SELECT ... FOR UPDATE чтобы исключить гонки при списаниях/начислениях.
    """
    q = select(User).where(User.id == user_id).with_for_update()
    res = await session.execute(q)
    user = res.scalar_one_or_none()
    if not user:
        raise UserNotFound(f"User not found: {user_id}")
    return user


async def _get_session_for_update(session: AsyncSession, match_token: str) -> PvpSession:
    q = select(PvpSession).where(PvpSession.match_token == match_token).with_for_update()
    res = await session.execute(q)
    sess = res.scalar_one_or_none()
    if not sess:
        raise SessionNotFound("Match session not found")
    return sess


def _is_expired(sess: PvpSession) -> bool:
    if sess.expires_at is None:
        return False
    now = datetime.now(timezone.utc)
    return sess.expires_at < now


# ----------------------------
# Public API
# ----------------------------

async def finish_live_pvp(
    session: AsyncSession,
    *,
    player1_id: int,
    player2_id: int,
    player1_clicks: int,
    player2_clicks: int,
    stake: int = 50000,
) -> LivePvpResult:
    """
    Финализация PvP Live (1v1) БЕЗ match_token:
    - проверяем пользователей
    - проверяем, что у обоих достаточно total_xp для ставки (если stake>0)
    - списываем ставки
    - если ничья: возвращаем ставки
      иначе: победитель получает банк (эквивалентно winner +stake, loser -stake)
    - сохраняем матч в pvp_matches и обновляем victories/best_result через CRUD
    """
    if player1_id == player2_id:
        raise InvalidPayload("player1_id and player2_id must be different")
    if player1_clicks < 0 or player2_clicks < 0:
        raise InvalidPayload("clicks must be >= 0")
    if stake < 0:
        raise InvalidPayload("stake must be >= 0")

    # одинаковый порядок блокировки строк → меньше шанс дедлоков
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

    # списываем ставки
    if stake > 0:
        u1.total_xp -= stake
        u2.total_xp -= stake

    # распределяем банк
    if outcome.is_draw:
        if stake > 0:
            u1.total_xp += stake
            u2.total_xp += stake
    else:
        # winner получает 2*stake
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


# ✅ ИМЕННО ЭТУ ФУНКЦИЮ ЖДЁТ РОУТЕР (ImportError был из-за её отсутствия)
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
    R0/R1 защита finish:
    - match_token обязателен
    - сессия должна существовать и быть active
    - нельзя finish дважды
    - учитываем expires_at
    - проверяем, что requester/opponent — участники сессии
    - после успешного finish → status=finished, finished_at=now
    """
    if requester_user_id == opponent_user_id:
        raise InvalidPayload("requester_user_id and opponent_user_id must be different")
    if requester_clicks < 0 or opponent_clicks < 0:
        raise InvalidPayload("clicks must be >= 0")
    if stake_fixed < 0:
        raise InvalidPayload("stake must be >= 0")

    sess = await _get_session_for_update(session, match_token)

    # expiry
    if _is_expired(sess):
        sess.status = "expired"
        await session.flush()
        raise SessionExpired("Match session expired")

    if sess.status != "active":
        raise SessionNotActive(f"Session is not active: {sess.status}")

    # участники
    players = {int(sess.player1_id), int(sess.player2_id)}
    if requester_user_id not in players or opponent_user_id not in players:
        raise InvalidPayload("requester/opponent are not participants of this session")

    # Приводим клики к player1/player2 порядку сессии
    if requester_user_id == int(sess.player1_id):
        player1_clicks = requester_clicks
        player2_clicks = opponent_clicks
    else:
        player1_clicks = opponent_clicks
        player2_clicks = requester_clicks

    # Маркируем finished до расчётов, пока строка залочена
    sess.status = "finished"
    sess.finished_at = datetime.now(timezone.utc)
    await session.flush()

    # Финансовая/стат-логика
    result = await finish_live_pvp(
        session,
        player1_id=int(sess.player1_id),
        player2_id=int(sess.player2_id),
        player1_clicks=int(player1_clicks),
        player2_clicks=int(player2_clicks),
        stake=int(stake_fixed),
    )
    try:
        sess.match_id = int(result.match_id)
    except Exception:
        sess.match_id = None
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
    """
    Challenge (асинхронный):
    - проверяем challenger/opponent
    - проверяем дневной лимит (5/день) для challenger
    - берём opponent.pvp_best_result
    - вычисляем win/lose
    - создаём запись challenge_matches + победы/best_result (внутри CRUD)
    """
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

    res = await session.execute(select(User).where(User.id == challenger_id))
    challenger_fresh = res.scalar_one()

    return ChallengeResult(
        match_id=match.id,
        challenger_id=challenger_id,
        opponent_id=opponent_id,
        challenger_clicks=challenger_clicks,
        opponent_best_result=opponent_best,
        is_win=outcome.is_win,
        victories_delta=outcome.victories_delta,
        challenger_total_xp=int(challenger_fresh.total_xp),
        challenger_best_result=int(challenger_fresh.pvp_best_result),
    )

