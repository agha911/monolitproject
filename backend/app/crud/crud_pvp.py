# backend/app/crud/crud_pvp.py
# CRUD для PvP Live + Challenge (асинхронный SQLAlchemy)

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Tuple
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select, desc, func, or_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.pvp_models import PvpMatch, ChallengeMatch, PvpChallengeAttempt, PvpWeeklySeason, PvpWeeklyLeaderboardRow
from app.models.pvp_anticheat_models import (
    PvpLiveTelemetry,
    PvpChallengeTelemetry,
    PvpCheatEvent,
)



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
    q = (
        select(ChallengeMatch)
        .where(or_(ChallengeMatch.challenger_id == challenger_id, ChallengeMatch.opponent_id == challenger_id))
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



BAKU_TZ = "Asia/Baku"


def _season_window_for_now(now_utc: datetime, tz_name: str = BAKU_TZ) -> tuple[datetime, datetime]:
    """
    Season: Monday 00:00 -> Saturday 23:59:59 (Asia/Baku)
    Returns window as UTC datetimes.
    """
    tz = ZoneInfo(tz_name)
    now_local = now_utc.astimezone(tz)

    # Monday = 0 ... Sunday = 6
    weekday = now_local.weekday()
    # Start of current week (Monday 00:00)
    start_local = (now_local.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=weekday))
    # End = Saturday 23:59:59
    end_local = (start_local + timedelta(days=5)).replace(hour=23, minute=59, second=59, microsecond=0)

    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


async def _try_advisory_lock(session: AsyncSession, lock_key: int = 91234567) -> bool:
    """
    Uses PG transaction-level advisory lock.
    Prevents double rollover in multi-worker deployments.
    """
    res = await session.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": int(lock_key)})
    return bool(res.scalar() or False)


async def get_current_weekly_season(session: AsyncSession) -> PvpWeeklySeason | None:
    q = (
        select(PvpWeeklySeason)
        .where(PvpWeeklySeason.status == "active")
        .order_by(PvpWeeklySeason.start_at.desc())
        .limit(1)
    )
    return (await session.execute(q)).scalar_one_or_none()


async def _next_season_no(session: AsyncSession) -> int:
    q = select(func.coalesce(func.max(PvpWeeklySeason.season_no), 0))
    mx = (await session.execute(q)).scalar_one() or 0
    return int(mx) + 1


async def _snapshot_top_for_season(
    session: AsyncSession,
    *,
    season_id: int,
    limit: int = 10,
) -> int:
    """
    Saves TOP-N users into pvp_weekly_leaderboard for the season.
    Ranking order = victories desc, best_result desc (same as current).
    Returns number of inserted rows.
    """
    top = await get_pvp_leaderboard_top(session, limit=limit)  # already exists
    inserted = 0
    rank = 1
    for u in top:
        row = PvpWeeklyLeaderboardRow(
            season_id=int(season_id),
            user_id=int(u.id),
            rank=int(rank),
            victories=int(getattr(u, "pvp_victories", 0) or 0),
            best_result=int(getattr(u, "pvp_best_result", 0) or 0),
        )
        session.add(row)
        inserted += 1
        rank += 1
    await session.flush()
    return inserted


async def rollover_weekly_season_if_needed(session: AsyncSession) -> dict:
    """
    Ensures there is an active season for current time.
    If the active season ended -> finalize + snapshot + reset victories + create next season.
    Must be called inside a transaction (session.begin()).
    """
    now = datetime.now(timezone.utc)

    # lock to avoid double rollover
    locked = await _try_advisory_lock(session)
    if not locked:
        # Another worker is doing it, just return current season info later
        cur = await get_current_weekly_season(session)
        return {"ok": True, "status": "locked_elsewhere", "season_id": int(cur.id) if cur else None}

    cur = await get_current_weekly_season(session)
    start_at, end_at = _season_window_for_now(now, BAKU_TZ)

    # If no season exists yet -> create season for current window
    if not cur:
        sn = await _next_season_no(session)
        cur = PvpWeeklySeason(season_no=sn, start_at=start_at, end_at=end_at, status="active")
        session.add(cur)
        await session.flush()
        return {"ok": True, "status": "created", "season_id": int(cur.id), "season_no": int(cur.season_no)}

    # If current season doesn't match current window (edge cases) we still keep it,
    # but rollover strictly when it ended.
    if cur.end_at and cur.end_at < now:
        # finalize
        cur.status = "finished"
        cur.finalized_at = now
        await session.flush()

        snap_count = await _snapshot_top_for_season(session, season_id=int(cur.id), limit=10)

        # reset victories
        await reset_weekly_pvp_victories_for_all(session)

        # create next season for the "current" window (now belongs to next cycle after end)
        # recompute window again (because now might still be after end within same week)
        # easiest: compute from now_local; if still past end, move to next monday.
        # We'll compute from now, but if now_local is Sunday, the window function still gives Monday-Sat of current week.
        # So we shift by +1 day until within window.
        probe = now
        for _ in range(8):
            s2, e2 = _season_window_for_now(probe, BAKU_TZ)
            if probe <= e2:
                start_at, end_at = s2, e2
                break
            probe = probe + timedelta(days=1)

        sn = await _next_season_no(session)
        new_season = PvpWeeklySeason(season_no=sn, start_at=start_at, end_at=end_at, status="active")
        session.add(new_season)
        await session.flush()

        return {
            "ok": True,
            "status": "rolled",
            "finished_season_id": int(cur.id),
            "finished_season_no": int(cur.season_no),
            "snapshot_rows": int(snap_count),
            "new_season_id": int(new_season.id),
            "new_season_no": int(new_season.season_no),
        }

    return {"ok": True, "status": "no_change", "season_id": int(cur.id), "season_no": int(cur.season_no)}


async def get_weekly_leaderboard_snapshot(
    session: AsyncSession,
    *,
    season_id: int,
    limit: int = 10,
) -> list[PvpWeeklyLeaderboardRow]:
    q = (
        select(PvpWeeklyLeaderboardRow)
        .where(PvpWeeklyLeaderboardRow.season_id == int(season_id))
        .order_by(PvpWeeklyLeaderboardRow.rank.asc())
        .limit(limit)
    )
    return list((await session.execute(q)).scalars().all())






async def upsert_live_telemetry(
    session: AsyncSession,
    *,
    session_id: int,
    match_token: str,
    user_id: int,
    player_slot: str,
    payload: dict,
    verdict,
) -> PvpLiveTelemetry:
    row = (
        await session.execute(
            select(PvpLiveTelemetry)
            .where(PvpLiveTelemetry.session_id == session_id)
            .where(PvpLiveTelemetry.user_id == user_id)
            .limit(1)
        )
    ).scalar_one_or_none()

    if not row:
        row = PvpLiveTelemetry(
            session_id=int(session_id),
            match_token=match_token,
            user_id=int(user_id),
            player_slot=player_slot,
        )
        session.add(row)

    row.reported_clicks = int(payload.get("reported_clicks", 0))
    row.validated_clicks = int(verdict.validated_clicks)
    row.client_started_at_ms = payload.get("client_started_at_ms")
    row.client_finished_at_ms = payload.get("client_finished_at_ms")
    row.tap_count = payload.get("tap_count")
    row.max_concurrent_touches = payload.get("max_concurrent_touches")
    row.avg_taps_per_sec = payload.get("avg_taps_per_sec")
    row.peak_taps_per_sec = payload.get("peak_taps_per_sec")
    row.send_batches_count = payload.get("send_batches_count")
    row.had_pauses = payload.get("had_pauses")
    row.pause_count = payload.get("pause_count")
    row.longest_pause_ms = payload.get("longest_pause_ms")
    row.suspicion_score = int(verdict.suspicion_score)
    row.confidence = float(verdict.confidence)
    row.is_suspicious = bool(verdict.is_suspicious)
    row.reason = verdict.reason
    row.flags_json = list(verdict.flags)
    row.raw_payload_json = payload

    await session.flush()
    return row


async def get_live_telemetry_map(
    session: AsyncSession,
    *,
    session_id: int,
) -> dict[int, PvpLiveTelemetry]:
    rows = (
        await session.execute(
            select(PvpLiveTelemetry).where(PvpLiveTelemetry.session_id == session_id)
        )
    ).scalars().all()
    return {int(r.user_id): r for r in rows}


async def create_challenge_telemetry(
    session: AsyncSession,
    *,
    attempt_id: int,
    challenger_id: int,
    opponent_id: int,
    payload: dict,
    verdict,
) -> PvpChallengeTelemetry:
    row = PvpChallengeTelemetry(
        attempt_id=int(attempt_id),
        challenger_id=int(challenger_id),
        opponent_id=int(opponent_id),
        reported_clicks=int(payload.get("reported_clicks", 0)),
        validated_clicks=int(verdict.validated_clicks),
        client_started_at_ms=payload.get("client_started_at_ms"),
        client_finished_at_ms=payload.get("client_finished_at_ms"),
        tap_count=payload.get("tap_count"),
        max_concurrent_touches=payload.get("max_concurrent_touches"),
        avg_taps_per_sec=payload.get("avg_taps_per_sec"),
        peak_taps_per_sec=payload.get("peak_taps_per_sec"),
        send_batches_count=payload.get("send_batches_count"),
        had_pauses=payload.get("had_pauses"),
        pause_count=payload.get("pause_count"),
        longest_pause_ms=payload.get("longest_pause_ms"),
        suspicion_score=int(verdict.suspicion_score),
        confidence=float(verdict.confidence),
        is_suspicious=bool(verdict.is_suspicious),
        reason=verdict.reason,
        flags_json=list(verdict.flags),
        raw_payload_json=payload,
    )
    session.add(row)
    await session.flush()
    return row


async def create_cheat_events_from_flags(
    session: AsyncSession,
    *,
    mode: str,
    user_id: int,
    flags: list[str],
    reason: str | None = None,
    session_id: int | None = None,
    attempt_id: int | None = None,
    details_json: dict | None = None,
) -> None:
    for flag in flags:
        session.add(
            PvpCheatEvent(
                mode=mode,
                event_code=flag,
                severity="high" if "limit" in flag or "touches" in flag else "medium",
                user_id=int(user_id),
                session_id=session_id,
                attempt_id=attempt_id,
                reason=reason,
                details_json=details_json,
            )
        )
    await session.flush()
