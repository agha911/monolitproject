# app/routers/pvp.py

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import get_async_session
from app.models.user import User
from app.models.pvp_models import PvpInvite, PvpQueue, PvpSession
from app.crud.user import get_user

from app.helpers.pvp_helpers import (
    baku_day_bounds,
    now_baku,
    calc_best_result_range,
)

from app.crud.crud_pvp import (
    get_pvp_leaderboard_top,
    get_pvp_rank_for_user,
    list_recent_pvp_matches_for_user,
    list_recent_challenge_matches_for_user,
    reset_weekly_pvp_victories_for_all,
    count_today_challenge_attempts,
)

from app.services.pvp_service import (
    finish_live_pvp_session,
    run_challenge,
    UserNotFound,
    InsufficientCoins,
    ChallengeLimitExceeded,
    InvalidPayload,
    SessionNotFound,
    SessionNotActive,
    SessionExpired,
)

router = APIRouter(prefix="/api/pvp", tags=["pvp"])


# ====== Config ======

PVP_ENABLED = True
PVP_DEFAULT_STAKE = 50000  # ✅ фиксированный стейк
PVP_MATCH_DURATION_SEC = 30
PVP_MULTITOUCH_LIMIT = 2
CHALLENGE_DAILY_LIMIT_DEFAULT = 5
CHALLENGE_RANGE_PCT_DEFAULT = 0.15

PVP_ADMIN_TOKEN = os.getenv("PVP_ADMIN_TOKEN", "")


# ====== Schemas ======

class LiveFinishRequest(BaseModel):
    telegram_id: int
    opponent_telegram_id: int
    match_token: str = Field(min_length=10, max_length=128)
    requester_clicks: int = Field(ge=0)
    opponent_clicks: int = Field(ge=0)


class ChallengeRunRequest(BaseModel):
    telegram_id: int
    opponent_telegram_id: int
    challenger_clicks: int = Field(ge=0)
    daily_limit: int = Field(default=CHALLENGE_DAILY_LIMIT_DEFAULT, ge=1, le=50)


class InviteCreateRequest(BaseModel):
    telegram_id: int
    ttl_seconds: int = Field(default=3600, ge=60, le=86400)


class InviteAcceptRequest(BaseModel):
    telegram_id: int
    invite_code: str = Field(min_length=6, max_length=64)


class InviteCancelRequest(BaseModel):
    telegram_id: int
    invite_code: str = Field(min_length=6, max_length=64)


class MatchmakingJoinRequest(BaseModel):
    telegram_id: int
    ttl_seconds: int = Field(default=120, ge=10, le=3600)


class MatchmakingLeaveRequest(BaseModel):
    telegram_id: int


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _gen_invite_code() -> str:
    return secrets.token_urlsafe(8).replace("-", "").replace("_", "")


def _gen_match_token() -> str:
    return secrets.token_urlsafe(24).replace("-", "").replace("_", "")


def _require_admin(x_admin_token: Optional[str]) -> None:
    if not PVP_ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail={"code": "ADMIN_DISABLED", "message": "PVP_ADMIN_TOKEN not set"})
    if not x_admin_token or x_admin_token != PVP_ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Invalid admin token"})


async def _cleanup_expired(session: AsyncSession) -> None:
    """
    Лёгкий best-effort cleanup без cron:
    - истёкшие invites: created -> expired
    - истёкшие queue: waiting -> expired
    - истёкшие sessions: active -> expired
    """
    now = datetime.now(timezone.utc)

    # invites
    inv_q = (
        select(PvpInvite)
        .where(PvpInvite.status == "created")
        .where(PvpInvite.expires_at.isnot(None))
        .where(PvpInvite.expires_at < now)
        .limit(200)
    )
    invs = (await session.execute(inv_q)).scalars().all()
    for inv in invs:
        inv.status = "expired"
    # queue
    q_q = (
        select(PvpQueue)
        .where(PvpQueue.status == "waiting")
        .where(PvpQueue.expires_at.isnot(None))
        .where(PvpQueue.expires_at < now)
        .limit(200)
    )
    qs = (await session.execute(q_q)).scalars().all()
    for q in qs:
        q.status = "expired"
    # sessions
    s_q = (
        select(PvpSession)
        .where(PvpSession.status == "active")
        .where(PvpSession.expires_at.isnot(None))
        .where(PvpSession.expires_at < now)
        .limit(200)
    )
    ss = (await session.execute(s_q)).scalars().all()
    for s in ss:
        s.status = "expired"

    await session.flush()


async def _require_registered_user(session: AsyncSession, telegram_id: int) -> User:
    """
    ✅ P1: больше НЕ создаём пустых пользователей тут.
    Если юзера нет — значит не прошёл стандартную регистрацию.
    """
    user = await get_user(session, telegram_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail={"code": "USER_NOT_REGISTERED", "message": "User is not registered. Call /api/user/register first."},
        )
    return user


# -----------------------------------------------------------------------------
# 0) Config
# -----------------------------------------------------------------------------

@router.get("/config")
async def get_config():
    return {
        "ok": True,
        "enabled": PVP_ENABLED,
        "stake_default": PVP_DEFAULT_STAKE,
        "challenge_daily_limit": CHALLENGE_DAILY_LIMIT_DEFAULT,
        "challenge_range_pct_default": CHALLENGE_RANGE_PCT_DEFAULT,
        "match_duration_sec": PVP_MATCH_DURATION_SEC,
        "multitouch_limit": PVP_MULTITOUCH_LIMIT,
    }


# -----------------------------------------------------------------------------
# 1) Live finish / Challenge run
# -----------------------------------------------------------------------------

@router.post("/live/finish")
async def live_finish(body: LiveFinishRequest, session: AsyncSession = Depends(get_async_session)):
    """
    ✅ Безопасно: финализация только по match_token и только для участников сессии.
    """
    await _cleanup_expired(session)

    u1 = await _require_registered_user(session, body.telegram_id)
    u2 = await _require_registered_user(session, body.opponent_telegram_id)

    try:
        result = await finish_live_pvp_session(
            session,
            match_token=body.match_token,
            requester_user_id=u1.id,
            opponent_user_id=u2.id,
            requester_clicks=body.requester_clicks,
            opponent_clicks=body.opponent_clicks,
            stake_fixed=PVP_DEFAULT_STAKE,
        )
        await session.commit()
        return {
            "ok": True,
            "match_id": result.match_id,
            "is_draw": result.is_draw,
            "winner_id": result.winner_id,
            "player1": {
                "user_id": result.player1_id,
                "clicks": result.player1_clicks,
                "coins_delta": result.player1_coins_delta,
                "total_xp": result.player1_total_xp,
            },
            "player2": {
                "user_id": result.player2_id,
                "clicks": result.player2_clicks,
                "coins_delta": result.player2_coins_delta,
                "total_xp": result.player2_total_xp,
            },
            "stake": result.stake,
        }
    except SessionNotFound:
        await session.rollback()
        raise HTTPException(status_code=404, detail={"code": "SESSION_NOT_FOUND", "message": "Match session not found"})
    except SessionExpired:
        await session.rollback()
        raise HTTPException(status_code=409, detail={"code": "SESSION_EXPIRED", "message": "Match session expired"})
    except SessionNotActive as e:
        await session.rollback()
        raise HTTPException(status_code=409, detail={"code": "SESSION_NOT_ACTIVE", "message": str(e)})
    except InsufficientCoins as e:
        await session.rollback()
        raise HTTPException(status_code=409, detail={"code": "INSUFFICIENT_COINS", "message": str(e)})
    except InvalidPayload as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail={"code": "INVALID_PAYLOAD", "message": str(e)})
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail={"code": "PVP_INTERNAL_ERROR", "message": str(e)})


@router.post("/challenge/run")
async def challenge_run(body: ChallengeRunRequest, session: AsyncSession = Depends(get_async_session)):
    challenger = await _require_registered_user(session, body.telegram_id)
    opponent = await _require_registered_user(session, body.opponent_telegram_id)

    try:
        result = await run_challenge(
            session,
            challenger_id=challenger.id,
            opponent_id=opponent.id,
            challenger_clicks=body.challenger_clicks,
            daily_limit=body.daily_limit,
        )
        await session.commit()
        return {
            "ok": True,
            "match_id": result.match_id,
            "is_win": result.is_win,
            "victories_delta": result.victories_delta,
            "challenger": {
                "user_id": result.challenger_id,
                "telegram_id": body.telegram_id,
                "clicks": result.challenger_clicks,
                "total_xp": result.challenger_total_xp,
                "best_result": result.challenger_best_result,
            },
            "opponent": {
                "user_id": result.opponent_id,
                "telegram_id": body.opponent_telegram_id,
                "best_result_used": result.opponent_best_result,
            },
        }
    except ChallengeLimitExceeded as e:
        await session.rollback()
        raise HTTPException(status_code=409, detail={"code": "CHALLENGE_LIMIT", "message": str(e)})
    except InvalidPayload as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail={"code": "INVALID_PAYLOAD", "message": str(e)})
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail={"code": "CHALLENGE_INTERNAL_ERROR", "message": str(e)})


# -----------------------------------------------------------------------------
# 2) Leaderboard + Me
# -----------------------------------------------------------------------------

@router.get("/leaderboard")
async def leaderboard(limit: int = 50, session: AsyncSession = Depends(get_async_session)):
    limit = max(1, min(limit, 200))
    users = await get_pvp_leaderboard_top(session, limit=limit)

    items: List[Dict[str, Any]] = []
    for u in users:
        items.append(
            {
                "user_id": u.id,
                "telegram_id": int(u.telegram_id),
                "username": u.username,
                "first_name": u.first_name,
                "last_name": u.last_name,
                "pvp_victories": int(getattr(u, "pvp_victories", 0) or 0),
                "pvp_best_result": int(getattr(u, "pvp_best_result", 0) or 0),
                "total_xp": int(getattr(u, "total_xp", 0) or 0),
            }
        )

    return {"ok": True, "items": items}


@router.get("/me")
async def me(telegram_id: int, session: AsyncSession = Depends(get_async_session)):
    user = await _require_registered_user(session, telegram_id)
    rank = await get_pvp_rank_for_user(session, user_id=user.id)

    return {
        "ok": True,
        "user_id": user.id,
        "telegram_id": int(user.telegram_id),
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "pvp_victories": int(getattr(user, "pvp_victories", 0) or 0),
        "pvp_best_result": int(getattr(user, "pvp_best_result", 0) or 0),
        "total_xp": int(getattr(user, "total_xp", 0) or 0),
        "rank": rank,
    }


# -----------------------------------------------------------------------------
# 3) Challenge status + opponent
# -----------------------------------------------------------------------------

@router.get("/challenge/status")
async def challenge_status(
    telegram_id: int,
    daily_limit: int = CHALLENGE_DAILY_LIMIT_DEFAULT,
    session: AsyncSession = Depends(get_async_session),
):
    user = await _require_registered_user(session, telegram_id)

    attempts_today = await count_today_challenge_attempts(session, challenger_id=user.id)
    _, end = baku_day_bounds()
    seconds_to_reset = int((end - now_baku()).total_seconds())
    if seconds_to_reset < 0:
        seconds_to_reset = 0

    remaining = max(0, daily_limit - attempts_today)
    return {
        "ok": True,
        "attempts_today": attempts_today,
        "daily_limit": daily_limit,
        "remaining": remaining,
        "seconds_to_reset": seconds_to_reset,
    }


@router.get("/challenge/opponent")
async def challenge_opponent(
    telegram_id: int,
    pct: float = CHALLENGE_RANGE_PCT_DEFAULT,
    session: AsyncSession = Depends(get_async_session),
):
    me_user = await _require_registered_user(session, telegram_id)

    my_best = int(getattr(me_user, "pvp_best_result", 0) or 0)
    low, high = calc_best_result_range(best_result=my_best, pct=float(pct), min_floor=0)

    q = (
        select(User)
        .where(User.id != me_user.id)
        .where(User.pvp_best_result >= low)
        .where(User.pvp_best_result <= high)
        .order_by(func.random())
        .limit(1)
    )
    opp = (await session.execute(q)).scalar_one_or_none()

    if not opp:
        low2, high2 = calc_best_result_range(best_result=my_best, pct=float(pct) * 2.0, min_floor=0)
        q2 = (
            select(User)
            .where(User.id != me_user.id)
            .where(User.pvp_best_result >= low2)
            .where(User.pvp_best_result <= high2)
            .order_by(func.random())
            .limit(1)
        )
        opp = (await session.execute(q2)).scalar_one_or_none()

    if not opp:
        q3 = (
            select(User)
            .where(User.id != me_user.id)
            .where(User.pvp_best_result >= 0)
            .order_by(func.random())
            .limit(1)
        )
        opp = (await session.execute(q3)).scalar_one_or_none()

    if not opp:
        raise HTTPException(status_code=404, detail={"code": "NO_OPPONENT", "message": "No suitable opponent found"})

    return {
        "ok": True,
        "opponent": {
            "user_id": opp.id,
            "telegram_id": int(opp.telegram_id),
            "username": opp.username,
            "first_name": opp.first_name,
            "last_name": opp.last_name,
            "pvp_best_result": int(getattr(opp, "pvp_best_result", 0) or 0),
            "pvp_victories": int(getattr(opp, "pvp_victories", 0) or 0),
        },
        "range": {"low": low, "high": high},
        "my_best_result": my_best,
    }


# -----------------------------------------------------------------------------
# 4) History
# -----------------------------------------------------------------------------

@router.get("/live/history")
async def live_history(
    telegram_id: int,
    limit: int = 20,
    offset: int = 0,
    session: AsyncSession = Depends(get_async_session),
):
    user = await _require_registered_user(session, telegram_id)

    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    matches = await list_recent_pvp_matches_for_user(session, user_id=user.id, limit=limit, offset=offset)

    items: List[Dict[str, Any]] = []
    for m in matches:
        items.append(
            {
                "id": m.id,
                "player1_id": m.player1_id,
                "player2_id": m.player2_id,
                "player1_clicks": m.player1_clicks,
                "player2_clicks": m.player2_clicks,
                "stake": m.stake,
                "winner_id": m.winner_id,
                "is_draw": m.is_draw,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
        )
    return {"ok": True, "items": items}


@router.get("/challenge/history")
async def challenge_history(
    telegram_id: int,
    limit: int = 20,
    offset: int = 0,
    session: AsyncSession = Depends(get_async_session),
):
    user = await _require_registered_user(session, telegram_id)

    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    matches = await list_recent_challenge_matches_for_user(session, user_id=user.id, limit=limit, offset=offset)

    items: List[Dict[str, Any]] = []
    for m in matches:
        items.append(
            {
                "id": m.id,
                "challenger_id": m.challenger_id,
                "opponent_id": m.opponent_id,
                "challenger_clicks": m.challenger_clicks,
                "opponent_best_result": m.opponent_best_result,
                "is_win": m.is_win,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
        )
    return {"ok": True, "items": items}


# -----------------------------------------------------------------------------
# 5) Invites (ORM)
# -----------------------------------------------------------------------------

@router.post("/invite/create")
async def invite_create(body: InviteCreateRequest, session: AsyncSession = Depends(get_async_session)):
    await _cleanup_expired(session)

    creator = await _require_registered_user(session, body.telegram_id)

    # stake фиксированный 50k, и для создания invite проверяем, что у создателя есть 50k
    if int(getattr(creator, "total_xp", 0) or 0) < PVP_DEFAULT_STAKE:
        raise HTTPException(status_code=409, detail={"code": "INSUFFICIENT_COINS", "message": "Not enough coins for stake"})

    code = _gen_invite_code()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=body.ttl_seconds)

    inv = PvpInvite(
        code=code,
        creator_user_id=creator.id,
        stake=PVP_DEFAULT_STAKE,
        status="created",
        expires_at=expires_at,
    )
    session.add(inv)

    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail={"code": "INVITE_CREATE_FAILED", "message": str(e)})

    return {
        "ok": True,
        "invite_code": code,
        "stake": PVP_DEFAULT_STAKE,
        "expires_at": expires_at.isoformat(),
        "start_param": f"pvp_{code}",
    }


@router.get("/invite/status")
async def invite_status(invite_code: str, session: AsyncSession = Depends(get_async_session)):
    await _cleanup_expired(session)

    inv = (await session.execute(select(PvpInvite).where(PvpInvite.code == invite_code).limit(1))).scalar_one_or_none()

    if not inv:
        raise HTTPException(status_code=404, detail={"code": "INVITE_NOT_FOUND", "message": "Invite not found"})

    return {
        "ok": True,
        "invite_code": inv.code,
        "status": inv.status,
        "stake": int(inv.stake or PVP_DEFAULT_STAKE),
        "creator_user_id": inv.creator_user_id,
        "opponent_user_id": inv.opponent_user_id,
        "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
        "accepted_at": inv.accepted_at.isoformat() if inv.accepted_at else None,
    }


@router.post("/invite/accept")
async def invite_accept(body: InviteAcceptRequest, session: AsyncSession = Depends(get_async_session)):
    """
    ✅ При accept создаём PvpSession и выдаём match_token.
    """
    await _cleanup_expired(session)

    opponent = await _require_registered_user(session, body.telegram_id)

    inv = (
        await session.execute(
            select(PvpInvite)
            .where(PvpInvite.code == body.invite_code)
            .with_for_update()
            .limit(1)
        )
    ).scalar_one_or_none()

    if not inv:
        raise HTTPException(status_code=404, detail={"code": "INVITE_NOT_FOUND", "message": "Invite not found"})

    if inv.status != "created":
        raise HTTPException(status_code=409, detail={"code": "INVITE_NOT_ACTIVE", "message": f"Invite is {inv.status}"})

    if inv.expires_at and inv.expires_at < datetime.now(timezone.utc):
        inv.status = "expired"
        await session.commit()
        raise HTTPException(status_code=409, detail={"code": "INVITE_EXPIRED", "message": "Invite expired"})

    if inv.creator_user_id == opponent.id:
        raise HTTPException(status_code=400, detail={"code": "INVALID_PAYLOAD", "message": "Cannot accept own invite"})

    creator = await _require_registered_user(session, telegram_id=int((await session.execute(select(User.telegram_id).where(User.id == inv.creator_user_id))).scalar_one_or_none() or 0))
    # ↑ safety: если вдруг creator удалён/битый — _require_registered_user отловит.

    # stake фиксированный 50k: проверяем балансы обеих сторон
    if int(getattr(creator, "total_xp", 0) or 0) < PVP_DEFAULT_STAKE:
        raise HTTPException(status_code=409, detail={"code": "CREATOR_INSUFFICIENT_COINS", "message": "Creator has not enough coins"})
    if int(getattr(opponent, "total_xp", 0) or 0) < PVP_DEFAULT_STAKE:
        raise HTTPException(status_code=409, detail={"code": "OPPONENT_INSUFFICIENT_COINS", "message": "Opponent has not enough coins"})

    inv.status = "accepted"
    inv.opponent_user_id = opponent.id
    inv.accepted_at = datetime.now(timezone.utc)
    inv.stake = PVP_DEFAULT_STAKE

    match_token = _gen_match_token()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=(PVP_MATCH_DURATION_SEC + 90))  # окно финализации

    sess = PvpSession(
        match_token=match_token,
        mode="invite",
        status="active",
        player1_id=inv.creator_user_id,
        player2_id=opponent.id,
        stake=PVP_DEFAULT_STAKE,
        invite_id=inv.id,
        expires_at=expires_at,
    )
    session.add(sess)

    await session.commit()

    return {
        "ok": True,
        "match_token": match_token,
        "stake": PVP_DEFAULT_STAKE,
        "expires_at": expires_at.isoformat(),
        "players": {
            "player1_user_id": inv.creator_user_id,
            "player2_user_id": opponent.id,
        },
    }


@router.post("/invite/cancel")
async def invite_cancel(body: InviteCancelRequest, session: AsyncSession = Depends(get_async_session)):
    await _cleanup_expired(session)

    user = await _require_registered_user(session, body.telegram_id)

    inv = (
        await session.execute(
            select(PvpInvite)
            .where(PvpInvite.code == body.invite_code)
            .with_for_update()
            .limit(1)
        )
    ).scalar_one_or_none()

    if not inv:
        raise HTTPException(status_code=404, detail={"code": "INVITE_NOT_FOUND", "message": "Invite not found"})

    if inv.creator_user_id != user.id:
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Not invite creator"})

    if inv.status != "created":
        raise HTTPException(status_code=409, detail={"code": "INVITE_NOT_ACTIVE", "message": f"Invite is {inv.status}"})

    inv.status = "cancelled"
    inv.cancelled_at = datetime.now(timezone.utc)

    await session.commit()
    return {"ok": True}


# -----------------------------------------------------------------------------
# 6) Matchmaking (DB queue)
# -----------------------------------------------------------------------------

@router.post("/matchmaking/join")
async def matchmaking_join(body: MatchmakingJoinRequest, session: AsyncSession = Depends(get_async_session)):
    await _cleanup_expired(session)

    user = await _require_registered_user(session, body.telegram_id)

    # stake фиксированный 50k: проверка баланса для участия
    if int(getattr(user, "total_xp", 0) or 0) < PVP_DEFAULT_STAKE:
        raise HTTPException(status_code=409, detail={"code": "INSUFFICIENT_COINS", "message": "Not enough coins for stake"})

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=body.ttl_seconds)

    stmt = pg_insert(PvpQueue).values(
        user_id=user.id,
        stake=PVP_DEFAULT_STAKE,
        status="waiting",
        expires_at=expires_at,
    ).on_conflict_do_update(
        index_elements=[PvpQueue.user_id],
        set_={
            "stake": PVP_DEFAULT_STAKE,
            "status": "waiting",
            "matched_user_id": None,
            "match_token": None,
            "expires_at": expires_at,
            "updated_at": func.now(),
        },
    )

    await session.execute(stmt)
    await session.commit()

    return {"ok": True, "status": "waiting", "stake": PVP_DEFAULT_STAKE, "expires_at": expires_at.isoformat()}


@router.post("/matchmaking/leave")
async def matchmaking_leave(body: MatchmakingLeaveRequest, session: AsyncSession = Depends(get_async_session)):
    await _cleanup_expired(session)

    user = await _require_registered_user(session, body.telegram_id)

    q = (
        await session.execute(
            select(PvpQueue)
            .where(PvpQueue.user_id == user.id)
            .with_for_update()
            .limit(1)
        )
    ).scalar_one_or_none()

    if not q:
        return {"ok": True, "status": "left"}

    q.status = "left"
    q.matched_user_id = None
    q.match_token = None
    await session.commit()
    return {"ok": True, "status": "left"}


@router.post("/matchmaking/poll")
async def matchmaking_poll(telegram_id: int, session: AsyncSession = Depends(get_async_session)):
    """
    Возвращает:
    - waiting: если пары нет
    - matched: если пара найдена (возвращаем match_token)
    """
    await _cleanup_expired(session)

    me = await _require_registered_user(session, telegram_id)

    # если я уже matched — отдадим токен
    my_row = (
        await session.execute(
            select(PvpQueue).where(PvpQueue.user_id == me.id).limit(1)
        )
    ).scalar_one_or_none()

    if my_row and my_row.status == "matched" and my_row.match_token:
        return {
            "ok": True,
            "status": "matched",
            "match_token": my_row.match_token,
            "opponent_user_id": my_row.matched_user_id,
            "stake": PVP_DEFAULT_STAKE,
            "match_duration_sec": PVP_MATCH_DURATION_SEC,
        }

    # если меня нет в очереди — считаем что не join
    if not my_row or my_row.status not in ("waiting", "matched"):
        return {"ok": True, "status": "not_in_queue"}

    # Лочим мою строку (я waiting)
    my_locked = (
        await session.execute(
            select(PvpQueue)
            .where(PvpQueue.user_id == me.id)
            .with_for_update()
            .limit(1)
        )
    ).scalar_one_or_none()

    if not my_locked or my_locked.status != "waiting":
        await session.commit()
        return {"ok": True, "status": "waiting"}

    # Ищем кандидата: waiting, не я, не истёк, stake фиксированный
    now = datetime.now(timezone.utc)
    cand_q = (
        select(PvpQueue)
        .where(PvpQueue.status == "waiting")
        .where(PvpQueue.user_id != me.id)
        .where(PvpQueue.stake == PVP_DEFAULT_STAKE)
        .where(and_(PvpQueue.expires_at.is_(None), True) | (PvpQueue.expires_at >= now))
        .order_by(PvpQueue.updated_at.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    candidate = (await session.execute(cand_q)).scalar_one_or_none()

    if not candidate:
        await session.commit()
        return {"ok": True, "status": "waiting"}

    # Матчим
    token = _gen_match_token()
    my_locked.status = "matched"
    my_locked.matched_user_id = candidate.user_id
    my_locked.match_token = token

    candidate.status = "matched"
    candidate.matched_user_id = my_locked.user_id
    candidate.match_token = token

    # Создаём сессию (валидная основа для finish)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=(PVP_MATCH_DURATION_SEC + 90))
    sess = PvpSession(
        match_token=token,
        mode="matchmaking",
        status="active",
        player1_id=my_locked.user_id,
        player2_id=candidate.user_id,
        stake=PVP_DEFAULT_STAKE,
        expires_at=expires_at,
    )
    session.add(sess)

    await session.commit()

    return {
        "ok": True,
        "status": "matched",
        "match_token": token,
        "opponent_user_id": int(candidate.user_id),
        "stake": PVP_DEFAULT_STAKE,
        "expires_at": expires_at.isoformat(),
        "match_duration_sec": PVP_MATCH_DURATION_SEC,
    }


# -----------------------------------------------------------------------------
# 7) Admin weekly reset
# -----------------------------------------------------------------------------

@router.post("/admin/reset-weekly")
async def admin_reset_weekly(
    x_admin_token: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_async_session),
):
    _require_admin(x_admin_token)
    await reset_weekly_pvp_victories_for_all(session)
    await session.commit()
    return {"ok": True}


