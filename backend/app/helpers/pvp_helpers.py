# backend/app/helpers/pvp_helpers.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple


# ---------------------------------------------------------------------
# Time helpers (Azerbaijan, UTC+4)
# ---------------------------------------------------------------------

AZ_TZ = timezone(timedelta(hours=4), name="AZT")


def az_now() -> datetime:
    """
    Текущее время в Азербайджане (UTC+4), aware datetime.
    """
    return datetime.now(AZ_TZ)


def az_day_bounds_utc(dt_az: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    """
    Возвращает (start_utc, end_utc) для суток по времени Азербайджана.
    Удобно для дневных лимитов challenge (5/день).

    end_utc — эксклюзивная граница (start + 1 day).
    """
    if dt_az is None:
        dt_az = az_now()

    # если пришёл dt без tzinfo, считаем, что это AZ
    if dt_az.tzinfo is None:
        dt_az = dt_az.replace(tzinfo=AZ_TZ)
    else:
        dt_az = dt_az.astimezone(AZ_TZ)

    start_az = dt_az.replace(hour=0, minute=0, second=0, microsecond=0)
    end_az = start_az + timedelta(days=1)

    start_utc = start_az.astimezone(timezone.utc)
    end_utc = end_az.astimezone(timezone.utc)
    return start_utc, end_utc


# ---------------------------------------------------------------------
# Matchmaking helper (Challenge opponent range)
# ---------------------------------------------------------------------

def calc_best_result_range(
    my_best: int,
    *,
    pct: float = 0.20,
    min_span: int = 20,
    min_low: int = 0,
) -> Tuple[int, int]:
    """
    Диапазон подбора оппонента для Challenge: best +/- pct,
    но не уже чем min_span.

    Пример: my_best=100, pct=0.2 => 80..120
    """
    my_best = int(my_best or 0)
    if my_best < 0:
        my_best = 0

    span = max(int(my_best * pct), min_span)
    low = max(min_low, my_best - span)
    high = my_best + span
    return low, high


# ---------------------------------------------------------------------
# PvP / Challenge outcomes
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class PvpOutcome:
    is_draw: bool
    winner_id: Optional[int]  # None if draw


@dataclass(frozen=True)
class PvpPayout:
    """
    Дельты (в монетах / total_xp), которые отражают итог матча:
    - winner: +stake
    - loser:  -stake
    - draw:    0
    """
    player1_delta: int
    player2_delta: int


@dataclass(frozen=True)
class ChallengeOutcome:
    is_win: bool
    victories_delta: int  # win=+1, lose=0


def resolve_pvp_outcome(
    *,
    player1_id: int,
    player2_id: int,
    player1_clicks: int,
    player2_clicks: int,
) -> PvpOutcome:
    """
    Определение исхода live PvP по кликам.
    """
    player1_clicks = int(player1_clicks)
    player2_clicks = int(player2_clicks)

    if player1_clicks == player2_clicks:
        return PvpOutcome(is_draw=True, winner_id=None)

    if player1_clicks > player2_clicks:
        return PvpOutcome(is_draw=False, winner_id=int(player1_id))

    return PvpOutcome(is_draw=False, winner_id=int(player2_id))


def calc_pvp_payout(
    *,
    player1_id: int,
    player2_id: int,
    outcome: PvpOutcome,
    stake: int,
) -> PvpPayout:
    """
    Пэйаут в терминах *дельт*:
      - победитель: +stake
      - проигравший: -stake
      - ничья: 0/0

    В твоём сервисе фактическое списание/возврат может делаться иначе,
    но эти дельты удобны для ответа/логов/тестов.
    """
    stake = int(stake)
    if stake < 0:
        stake = 0

    if outcome.is_draw:
        return PvpPayout(player1_delta=0, player2_delta=0)

    if outcome.winner_id == int(player1_id):
        return PvpPayout(player1_delta=stake, player2_delta=-stake)

    return PvpPayout(player1_delta=-stake, player2_delta=stake)


def resolve_challenge_outcome(
    *,
    challenger_clicks: int,
    opponent_best_result: int,
) -> ChallengeOutcome:
    """
    Challenge: сравниваем клики challenger с best_result оппонента.
    По твоей текущей договорённости:
      - победа: +1 victory
      - поражение: 0
    """
    challenger_clicks = int(challenger_clicks)
    opponent_best_result = int(opponent_best_result)

    is_win = challenger_clicks > opponent_best_result
    return ChallengeOutcome(is_win=is_win, victories_delta=(1 if is_win else 0))


    if high < low:
        high = low

    return low, high
