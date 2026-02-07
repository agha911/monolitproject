# backend/app/services/pvp_service.py
# Сервис-логика поверх CRUD: атомарные изменения total_xp (монеты), победы/рекорды, лимиты Challenge.

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User
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
    Финализация PvP Live (1v1):
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

    # Гарантируем одинаковый порядок блокировки строк, чтобы не словить дедлок
    first_id, second_id = (player1_id, player2_id) if player1_id < player2_id else (player2_id, player1_id)

    # Лочим обоих пользователей
    u_first = await _get_user_for_update(session, first_id)
    u_second = await _get_user_for_update(session, second_id)

    # Привязываем к исходным ролям
    if u_first.id == player1_id:
        u1, u2 = u_first, u_second
    else:
        u1, u2 = u_second, u_first

    # Проверка балансов
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

    # Денежная часть — атомарно:
    # 1) списать ставки
    if stake > 0:
        u1.total_xp -= stake
        u2.total_xp -= stake

    # 2) распределить банк
    # Для ничьей payout дельты 0 — ниже ничего не поменяется,
    # но нам надо вернуть ставки: проще сделать возвратом stake каждому.
    if outcome.is_draw:
        if stake > 0:
            u1.total_xp += stake
            u2.total_xp += stake
    else:
        # winner получает банк (2*stake)
        # В 1v1 эквивалентно winner_total_xp += 2*stake
        if payout.player1_delta > 0:
            u1.total_xp += (2 * stake)
        else:
            u2.total_xp += (2 * stake)

    # Записываем матч и обновляем victories/best_result (внутри create_pvp_match)
    match = await create_pvp_match(
        session,
        player1_id=player1_id,
        player2_id=player2_id,
        player1_clicks=player1_clicks,
        player2_clicks=player2_clicks,
        stake=stake,
    )

    # Фиксируем изменения, но коммит пусть делает внешний слой (роутер),
    # чтобы можно было объединять с другими действиями.
    await session.flush()

    # Дельты относительно состояния "до матча" по 1v1:
    # победа: winner +stake, loser -stake
    # ничья: 0/0
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

    # Лочим challenger, чтобы не было гонок по best_result/победам (и вдруг дальше добавишь награды)
    challenger = await _get_user_for_update(session, challenger_id)

    # opponent можно не лочить (мы читаем только best_result),
    # но чтобы избежать “скачков” в момент обновления — можно залочить и его.
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

    # challenger.best_result мог обновиться в CRUD (через UPDATE)
    # но объект в сессии может быть не обновлён — перечитаем быстро
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
