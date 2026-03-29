# backend/app/helpers/pvp_helpers.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, List, Any


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







@dataclass(frozen=True)
class TelemetryVerdict:
    validated_clicks: int
    suspicion_score: int
    confidence: float
    is_suspicious: bool
    reason: str | None
    flags: list[str]


def review_telemetry(
    *,
    reported_clicks: int,
    telemetry: Any | None,
    server_started_at: datetime,
    server_finished_at: datetime,
    max_touches: int = 2,
    max_avg_tps: float = 16.0,
    max_peak_tps: float = 22.0,
    duration_tolerance_sec: float = 4.0,
    click_grace: int = 20,
) -> TelemetryVerdict:
    reported_clicks = max(0, int(reported_clicks or 0))
    score = 0
    flags: list[str] = []

    if telemetry is None:
        t = {}
    elif hasattr(telemetry, "model_dump"):
        t = telemetry.model_dump(exclude_none=True)
    elif isinstance(telemetry, dict):
        t = telemetry
    else:
        t = {}

    server_elapsed = max(0.0, (server_finished_at - server_started_at).total_seconds())
    server_hard_limit = int(server_elapsed * max_touches * max_avg_tps) + click_grace

    tap_count = t.get("tap_count")
    max_concurrent_touches = t.get("max_concurrent_touches")
    avg_taps_per_sec = t.get("avg_taps_per_sec")
    peak_taps_per_sec = t.get("peak_taps_per_sec")
    had_pauses = t.get("had_pauses")
    pause_count = t.get("pause_count")
    longest_pause_ms = t.get("longest_pause_ms")
    client_started_at_ms = t.get("client_started_at_ms")
    client_finished_at_ms = t.get("client_finished_at_ms")

    if reported_clicks > server_hard_limit:
        score += 100
        flags.append("server_hard_limit_exceeded")

    if tap_count is not None and int(tap_count) != reported_clicks:
        score += 70
        flags.append("tap_count_mismatch")

    if max_concurrent_touches is not None and int(max_concurrent_touches) > max_touches:
        score += 100
        flags.append("too_many_touches")

    if avg_taps_per_sec is not None and float(avg_taps_per_sec) > max_avg_tps:
        score += 80
        flags.append("avg_tps_too_high")

    if peak_taps_per_sec is not None and float(peak_taps_per_sec) > max_peak_tps:
        score += 80
        flags.append("peak_tps_too_high")

    if (
        client_started_at_ms is not None
        and client_finished_at_ms is not None
        and int(client_finished_at_ms) >= int(client_started_at_ms)
    ):
        client_elapsed = (int(client_finished_at_ms) - int(client_started_at_ms)) / 1000.0
        if abs(client_elapsed - server_elapsed) > duration_tolerance_sec:
            score += 35
            flags.append("client_server_duration_mismatch")

    if bool(had_pauses) is False and reported_clicks >= 180 and float(avg_taps_per_sec or 0) >= 9.0:
        score += 20
        flags.append("no_pauses_high_speed")

    if pause_count is not None and int(pause_count) == 0 and reported_clicks >= 220:
        score += 20
        flags.append("zero_pause_pattern")

    if longest_pause_ms is not None and int(longest_pause_ms) < 0:
        score += 25
        flags.append("invalid_pause_value")

    is_suspicious = score >= 100
    validated_clicks = 0 if is_suspicious else min(reported_clicks, server_hard_limit)
    confidence = min(1.0, round(score / 100.0, 2))
    reason = flags[0] if flags else None

    return TelemetryVerdict(
        validated_clicks=validated_clicks,
        suspicion_score=score,
        confidence=confidence,
        is_suspicious=is_suspicious,
        reason=reason,
        flags=flags,
    )
