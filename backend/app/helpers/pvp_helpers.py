# backend/app/helpers/pvp_helpers.py
# Хелперы для PvP Live + Challenge: расчет исхода, лимиты, подбор, недели (UTC+4)

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, date
from typing import Optional, Tuple


# Твой проект живёт по Баку: UTC+4 (без DST)
BAKU_TZ = timezone(timedelta(hours=4))


# ----------------------------
# Results / DTO
# ----------------------------

@dataclass(frozen=True)
class PvpOutcome:
    is_draw: bool
    winner_id: Optional[int]
    loser_id: Optional[int]


@dataclass(frozen=True)
class PvpPayout:
    """
    Денежные изменения по матчу (в монетах приложения).
    Важно: логика списаний/начислений должна быть атомарной в сервисе.
    """
    stake: int
    bank: int
    player1_delta: int
    player2_delta: int


@dataclass(frozen=True)
class ChallengeOutcome:
    is_win: bool
    victories_delta: int  # +1 при win, иначе 0


# ----------------------------
# Core logic
# ----------------------------

def resolve_pvp_outcome(
    *,
    player1_id: int,
    player2_id: int,
    player1_clicks: int,
    player2_clicks: int,
) -> PvpOutcome:
    """
    Определяет победителя/ничью для PvP Live.
    """
    if player1_id == player2_id:
        raise ValueError("player1_id and player2_id must be different")

    if player1_clicks < 0 or player2_clicks < 0:
        raise ValueError("clicks must be >= 0")

    if player1_clicks == player2_clicks:
        return PvpOutcome(is_draw=True, winner_id=None, loser_id=None)

    if player1_clicks > player2_clicks:
        return PvpOutcome(is_draw=False, winner_id=player1_id, loser_id=player2_id)

    return PvpOutcome(is_draw=False, winner_id=player2_id, loser_id=player1_id)


def calc_pvp_payout(
    *,
    player1_id: int,
    player2_id: int,
    outcome: PvpOutcome,
    stake: int = 50000,
) -> PvpPayout:
    """
    Расчёт изменения баланса по PvP Live:

    - ставка по умолчанию 50k с игрока
    - ничья -> возврат ставок
    - победа -> банк делится поровну победителям
      (в твоей механике: команды 1–2 человека; на уровне 1v1 это значит победитель получает весь банк,
       но если будет 2v2, сервис сможет разделить между победителями поровну)

    Тут мы считаем ДЕЛЬТЫ для 1v1:
      - ничья: player1_delta=0, player2_delta=0 (если ранее списал stake, то сервис делает возврат)
      - победа: winner_delta=+stake, loser_delta=-stake (эквивалент: loser теряет ставку, winner получает ставку оппонента)
    """
    if stake < 0:
        raise ValueError("stake must be >= 0")
    if player1_id == player2_id:
        raise ValueError("player1_id and player2_id must be different")

    bank = stake * 2

    if outcome.is_draw:
        # При ничьей: деньги возвращаются -> итоговая дельта 0, если сервис списывал и возвращал
        return PvpPayout(
            stake=stake,
            bank=bank,
            player1_delta=0,
            player2_delta=0,
        )

    if outcome.winner_id is None or outcome.loser_id is None:
        raise ValueError("invalid outcome: winner/loser required when not draw")

    # 1v1: winner получает ставку оппонента, loser теряет свою ставку
    if outcome.winner_id == player1_id:
        return PvpPayout(stake=stake, bank=bank, player1_delta=+stake, player2_delta=-stake)

    if outcome.winner_id == player2_id:
        return PvpPayout(stake=stake, bank=bank, player1_delta=-stake, player2_delta=+stake)

    raise ValueError("invalid outcome: winner_id must be one of players")


def resolve_challenge_outcome(
    *,
    challenger_clicks: int,
    opponent_best_result: int,
) -> ChallengeOutcome:
    """
    Challenge: победа если challenger_clicks > opponent_best_result
    Победа: +1 victory
    Поражение: 0
    """
    if challenger_clicks < 0 or opponent_best_result < 0:
        raise ValueError("values must be >= 0")

    is_win = challenger_clicks > opponent_best_result
    return ChallengeOutcome(is_win=is_win, victories_delta=1 if is_win else 0)


# ----------------------------
# Limits / time helpers
# ----------------------------

def now_baku() -> datetime:
    return datetime.now(tz=BAKU_TZ)


def baku_day_bounds(dt: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    """
    Возвращает (start_of_day, end_of_day) в TZ Баку.
    end_of_day = start + 1 day.
    """
    dt = dt or now_baku()
    dt_local = dt.astimezone(BAKU_TZ)
    start = dt_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


def is_challenge_limit_exceeded(*, attempts_today: int, limit_per_day: int = 5) -> bool:
    return attempts_today >= limit_per_day


# ----------------------------
# Weekly reset helpers
# ----------------------------

def week_window_utc4(dt: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    """
    Окно "недельного турнира" / weekly reset по твоему правилу:
    понедельник 00:00 — суббота 23:59 (UTC+4).

    Возвращаем (week_start, week_end_exclusive), где:
    - week_start: понедельник 00:00
    - week_end_exclusive: воскресенье 00:00 (т.е. сразу после субботы 23:59:59.999...)
    """
    dt = dt or now_baku()
    dt_local = dt.astimezone(BAKU_TZ)

    # weekday(): Monday=0 ... Sunday=6
    monday = dt_local - timedelta(days=dt_local.weekday())
    week_start = monday.replace(hour=0, minute=0, second=0, microsecond=0)

    # конец "соревновательной недели" — воскресенье 00:00
    week_end_exclusive = week_start + timedelta(days=6)  # monday->sunday 00:00? нет, это saturday 00:00
    # Правильно: monday 00:00 + 6 days = sunday 00:00? Проверим:
    # Monday + 6 days = Sunday (weekday 6) same time => Sunday 00:00 ✅
    # Значит окно понедельник 00:00 .. воскресенье 00:00 (не включает воскресенье)
    return week_start, week_end_exclusive


def is_reset_moment(dt: Optional[datetime] = None) -> bool:
    """
    Триггерный момент сброса — начало новой недели: понедельник 00:00 (UTC+4).
    """
    dt = dt or now_baku()
    dt_local = dt.astimezone(BAKU_TZ)
    return dt_local.weekday() == 0 and dt_local.hour == 0 and dt_local.minute == 0


# ----------------------------
# Matchmaking helper
# ----------------------------

def calc_best_result_range(
    *,
    best_result: int,
    pct: float,
    min_floor: int = 0,
) -> Tuple[int, int]:
    """
    Диапазон для Challenge подбора по best_result:
    best_result ± pct (например 0.15 = ±15%)
    """
    if best_result < 0:
        raise ValueError("best_result must be >= 0")
    if pct < 0:
        raise ValueError("pct must be >= 0")

    low = int(best_result * (1.0 - pct))
    high = int(best_result * (1.0 + pct))

    if low < min_floor:
        low = min_floor

    if high < low:
        high = low

    return low, high
