# app/routers/pvp.py
# PvP / Challenge router (в стиле challenge.py)
# Clean version: no raw SQL, uses ORM models for invites + queue.

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import get_async_session
from app.models.user import User
from app.models.pvp_models import PvpInvite, PvpQueue  # <-- теперь ORM
from app.crud.user import get_user  # получить user по telegram_id

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
    finish_live_pvp,
    run_challenge,
    UserNotFound,
    InsufficientCoins,
    ChallengeLimitExceeded,
    InvalidPayload,
)

router = APIRouter(prefix="/api/pvp", tags=["pvp"])


# ====== Config ======

PVP_ENABLED = True
PVP_DEFAULT_STAKE = 50000
PVP_MATCH_DURATION_SEC = 30
PVP_MULTITOUCH_LIMIT = 2
CHALLENGE_DAILY_LIMIT_DEFAULT = 5
CHALLENGE_RANGE_PCT_DEFAULT = 0.15

# admin token (Render env: PVP_ADMIN_TOKEN=...)
PVP_ADMIN_TOKEN = os.getenv("PVP_ADMIN_TOKEN", "")


# ====== Schemas ======

class LiveFinishRequest(BaseModel):
    telegram_id: int
    opponent_telegram_id: int
    player1_clicks: int = Field(ge=0)
    player2_clicks: int = Field(ge=0)
    stake: int = Field(default=PVP_DEFAULT_STAKE, ge=0)


class ChallengeRunRequest(BaseModel):
    telegram_id: int
    opponent_telegram_id: int
    challenger_clicks: int = Field(ge=0)
    daily_limit: int = Field(default=CHALLENGE_DAILY_LIMIT_DEFAULT, ge=1, le=50)


class InviteCreateRequest(BaseModel):
    telegram_id: int
    stake: int = Field(default=PVP_DEFAULT_STAKE, ge=0)
    ttl_seconds: int = Field(default=3600, ge=60, le=86400)


class InviteAcceptRequest(BaseModel):
    telegram_id: int
    invite_code: str = Field(min_length=6, max_length=64)


class InviteCancelRequest(BaseModel):
    telegram_id: int
    invite_code: str = Field(min_length=6, max_length=64)


class MatchmakingJoinRequest(BaseModel):
    telegram_id: int
    stake: int = Field(default=PVP_DEFAULT_STAKE, ge=0)
    ttl_seconds: int = Field(default=120, ge=10, le=3600)


class MatchmakingLeaveRequest(BaseModel):
    telegram_id: int


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _gen_invite_code() -> str:
    return secrets.token_urlsafe(8).replace("-", "").replace("_", "")


def _require_admin(x_admin_token: Optional[str]) -> None:
    if not PVP_ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail={"code": "ADMIN_DISABLED", "message": "PVP_ADMIN_TOKEN not set"})
    if not x_admin_token or x_admin_token != PVP_ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Invalid admin token"})


async def _get_or_create_user_with_bonus(session: AsyncSession, telegram_id: int) -> User:
    """
    Для invite-онбординга: если пользователя нет — создаём и выдаём 50k total_xp.
    """
    user = await get_user(session, telegram_id)
    if user:
        return user

    user = User(telegram_id=telegram_id, total_xp=PVP_DEFAULT_STAKE)
    session.add(user)
    await session.flush()  # нужен user.id
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
    u1 = await get_user(session, body.telegram_id)
    if not u1:
        raise HTTPException(status_code=404, detail="User not found")

    u2 = await get_user(session, body.opponent_telegram_id)
    if not u2:
        raise HTTPException(status_code=404, detail="Opponent not found")

    try:
        result = await finish_live_pvp(
            session,
            player1_id=u1.id,
            player2_id=u2.id,
            player1_clicks=body.player1_clicks,
            player2_clicks=body.player2_clicks,
            stake=body.stake,
        )
        await session.commit()
        return {
            "ok": True,
            "match_id": result.match_id,
            "is_draw": result.is_draw,
            "winner_id": result.winner_id,  # user.id
            "player1": {
                "user_id": result.player1_id,
                "telegram_id": body.telegram_id,
                "clicks": result.player1_clicks,
                "coins_delta": result.player1_coins_delta,
                "total_xp": result.player1_total_xp,
            },
            "player2": {
                "user_id": result.player2_id,
                "telegram_id": body.opponent_telegram_id,
                "clicks": result.player2_clicks,
                "coins_delta": result.player2_coins_delta,
                "total_xp": result.player2_total_xp,
            },
            "stake": result.stake,
        }
    except UserNotFound:
        await session.rollback()
        raise HTTPException(status_code=404, detail="User not found")
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
    challenger = await get_user(session, body.telegram_id)
    if not challenger:
        raise HTTPException(status_code=404, detail="User not found")

    opponent = await get_user(session, body.opponent_telegram_id)
    if not opponent:
        raise HTTPException(status_code=404, detail="Opponent not found")

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
    user = await get_user(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

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
    user = await get_user(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

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
    me_user = await get_user(session, telegram_id)
    if not me_user:
        raise HTTPException(status_code=404, detail="User not found")

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
    user = await get_user(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

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
    user = await get_user(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

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
    creator = await get_user(session, body.telegram_id)
    if not creator:
        raise HTTPException(status_code=404, detail="User not found")

    if body.stake > 0 and int(getattr(creator, "total_xp", 0) or 0) < body.stake:
        raise HTTPException(status_code=409, detail={"code": "INSUFFICIENT_COINS", "message": "Not enough coins for stake"})

    code = _gen_invite_code()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=body.ttl_seconds)

    inv = PvpInvite(
        code=code,
        creator_user_id=creator.id,
        stake=body.stake,
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
        "stake": body.stake,
        "expires_at": expires_at.isoformat(),
        "start_param": f"pvp_{code}",
    }


@router.get("/invite/status")
async def invite_status(invite_code: str, session: AsyncSession = Depends(get_async_session)):
    inv = (
        await session.execute(select(PvpInvite).where(PvpInvite.code == invite_code).limit(1))
    ).scalar_one_or_none()

    if not inv:
        raise HTTPException(status_code=404, detail={"code": "INVITE_NOT_FOUND", "message": "Invite not found"})

    # авто-expire (best effort)
    if inv.status == "created" and inv.expires_at and inv.expires_at <= datetime.now(timezone.utc):
        inv.status = "expired"
        try:
            await session.commit()
        except Exception:
            await session.rollback()

    return {
        "ok": True,
        "invite": {
            "code": inv.code,
            "creator_user_id": inv.creator_user_id,
            "opponent_user_id": inv.opponent_user_id,
            "stake": inv.stake,
            "status": inv.status,
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
            "accepted_at": inv.accepted_at.isoformat() if inv.accepted_at else None,
            "cancelled_at": inv.cancelled_at.isoformat() if inv.cancelled_at else None,
            "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
        },
    }


@router.post("/invite/cancel")
async def invite_cancel(body: InviteCancelRequest, session: AsyncSession = Depends(get_async_session)):
    user = await get_user(session, body.telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    inv = (
        await session.execute(
            select(PvpInvite)
            .where(PvpInvite.code == body.invite_code)
            .where(PvpInvite.creator_user_id == user.id)
            .with_for_update()
            .limit(1)
        )
    ).scalar_one_or_none()

    if not inv:
        raise HTTPException(status_code=404, detail={"code": "INVITE_NOT_FOUND", "message": "Invite not found"})

    if inv.status != "created":
        raise HTTPException(status_code=409, detail={"code": "INVITE_NOT_CANCELLABLE", "message": f"Invite status = {inv.status}"})

    inv.status = "cancelled"
    inv.cancelled_at = datetime.now(timezone.utc)

    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail={"code": "INVITE_CANCEL_FAILED", "message": str(e)})

    return {"ok": True, "invite_code": body.invite_code, "status": inv.status}


@router.post("/invite/accept")
async def invite_accept(body: InviteAcceptRequest, session: AsyncSession = Depends(get_async_session)):
    """
    Invite accept:
    - если пользователя нет -> создаём и начисляем 50k total_xp (как ты зафиксировал)
    - проверяем ставку у принимающего
    - лочим invite, чтобы не приняли дважды
    """
    user = await _get_or_create_user_with_bonus(session, body.telegram_id)

    inv = (
        await session.execute(
            select(PvpInvite)
            .where(PvpInvite.code == body.invite_code)
            .with_for_update()
            .limit(1)
        )
    ).scalar_one_or_none()

    if not inv:
        await session.rollback()
        raise HTTPException(status_code=404, detail={"code": "INVITE_NOT_FOUND", "message": "Invite not found"})

    if inv.status != "created":
        await session.rollback()
        raise HTTPException(status_code=409, detail={"code": "INVITE_NOT_ACTIVE", "message": f"Invite status = {inv.status}"})

    if inv.expires_at and inv.expires_at <= datetime.now(timezone.utc):
        inv.status = "expired"
        await session.commit()
        raise HTTPException(status_code=409, detail={"code": "INVITE_EXPIRED", "message": "Invite expired"})

    stake = int(inv.stake or 0)

    if stake > 0 and int(getattr(user, "total_xp", 0) or 0) < stake:
        await session.rollback()
        raise HTTPException(status_code=409, detail={"code": "INSUFFICIENT_COINS", "message": "Not enough coins to accept stake"})

    inv.opponent_user_id = user.id
    inv.status = "accepted"
    inv.accepted_at = datetime.now(timezone.utc)

    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail={"code": "INVITE_ACCEPT_FAILED", "message": str(e)})

    return {
        "ok": True,
        "invite_code": body.invite_code,
        "stake": stake,
        "creator_user_id": inv.creator_user_id,
        "opponent_user_id": user.id,
        "match_duration_sec": PVP_MATCH_DURATION_SEC,
    }


# -----------------------------------------------------------------------------
# 6) Matchmaking queue (ORM + UPSERT + SKIP LOCKED)
# -----------------------------------------------------------------------------

@router.post("/matchmaking/join")
async def matchmaking_join(body: MatchmakingJoinRequest, session: AsyncSession = Depends(get_async_session)):
    user = await get_user(session, body.telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if body.stake > 0 and int(getattr(user, "total_xp", 0) or 0) < body.stake:
        raise HTTPException(status_code=409, detail={"code": "INSUFFICIENT_COINS", "message": "Not enough coins for stake"})

    # TTL мы храним только как информацию на фронт (таблица не имеет expires_at),
    # очистку "старых" waiting можно делать позже отдельным джобом/эндпоинтом.
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=body.ttl_seconds)

    stmt = pg_insert(PvpQueue).values(
        user_id=user.id,
        stake=body.stake,
        status="waiting",
        matched_user_id=None,
        match_token=None,
    ).on_conflict_do_update(
        index_elements=[PvpQueue.user_id],
        set_={
            "stake": body.stake,
            "status": "waiting",
            "matched_user_id": None,
            "match_token": None,
            "updated_at": func.now(),
        },
    )

    try:
        await session.execute(stmt)
        await session.commit()
        return {
            "ok": True,
            "status": "waiting",
            "stake": body.stake,
            "expires_at": expires_at.isoformat(),
            "poll_hint_seconds": 1,
        }
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail={"code": "MATCHMAKING_JOIN_FAILED", "message": str(e)})


@router.post("/matchmaking/leave")
async def matchmaking_leave(body: MatchmakingLeaveRequest, session: AsyncSession = Depends(get_async_session)):
    user = await get_user(session, body.telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        q = (
            await session.execute(
                select(PvpQueue).where(PvpQueue.user_id == user.id).limit(1)
            )
        ).scalar_one_or_none()

        if q and q.status == "waiting":
            await session.delete(q)

        await session.commit()
        return {"ok": True, "status": "left"}
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail={"code": "MATCHMAKING_LEAVE_FAILED", "message": str(e)})


@router.post("/matchmaking/poll")
async def matchmaking_poll(telegram_id: int, session: AsyncSession = Depends(get_async_session)):
    """
    Poll:
    - если уже matched -> вернуть opponent + match_token
    - если waiting -> попытаться сматчить с другим waiting:
        SELECT ... FOR UPDATE SKIP LOCKED
    """
    me_user = await get_user(session, telegram_id)
    if not me_user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        me_q = (
            await session.execute(select(PvpQueue).where(PvpQueue.user_id == me_user.id).limit(1))
        ).scalar_one_or_none()

        if not me_q:
            return {"ok": True, "status": "not_in_queue"}

        if me_q.status == "matched" and me_q.matched_user_id and me_q.match_token:
            opp = (
                await session.execute(select(User).where(User.id == me_q.matched_user_id).limit(1))
            ).scalar_one_or_none()

            return {
                "ok": True,
                "status": "matched",
                "stake": int(me_q.stake or 0),
                "match_token": me_q.match_token,
                "opponent": {
                    "user_id": me_q.matched_user_id,
                    "telegram_id": int(opp.telegram_id) if opp else None,
                    "username": opp.username if opp else None,
                    "first_name": opp.first_name if opp else None,
                    "last_name": opp.last_name if opp else None,
                },
                "match_duration_sec": PVP_MATCH_DURATION_SEC,
            }

        if me_q.status != "waiting":
            return {"ok": True, "status": me_q.status}

        # lock my row
        me_locked = (
            await session.execute(
                select(PvpQueue)
                .where(PvpQueue.user_id == me_user.id)
                .where(PvpQueue.status == "waiting")
                .with_for_update()
                .limit(1)
            )
        ).scalar_one_or_none()
        if not me_locked:
            await session.commit()
            return {"ok": True, "status": "waiting"}

        # find candidate (skip locked)
        cand = (
            await session.execute(
                select(PvpQueue)
                .where(PvpQueue.status == "waiting")
                .where(PvpQueue.user_id != me_user.id)
                .order_by(PvpQueue.created_at.asc())
                .with_for_update(skip_locked=True)
                .limit(1)
            )
        ).scalar_one_or_none()

        if not cand:
            await session.commit()
            return {"ok": True, "status": "waiting"}

        match_token = secrets.token_urlsafe(12)

        # stake strategy: use my stake (как было)
        stake = int(me_locked.stake or 0)

        me_locked.status = "matched"
        me_locked.matched_user_id = cand.user_id
        me_locked.match_token = match_token

        cand.status = "matched"
        cand.matched_user_id = me_user.id
        cand.match_token = match_token

        opp_user = (
            await session.execute(select(User).where(User.id == cand.user_id).limit(1))
        ).scalar_one_or_none()

        await session.commit()

        return {
            "ok": True,
            "status": "matched",
            "stake": stake,
            "match_token": match_token,
            "opponent": {
                "user_id": cand.user_id,
                "telegram_id": int(opp_user.telegram_id) if opp_user else None,
                "username": opp_user.username if opp_user else None,
                "first_name": opp_user.first_name if opp_user else None,
                "last_name": opp_user.last_name if opp_user else None,
            },
            "match_duration_sec": PVP_MATCH_DURATION_SEC,
        }

    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail={"code": "MATCHMAKING_POLL_FAILED", "message": str(e)})


# -----------------------------------------------------------------------------
# 7) Weekly reset admin
# -----------------------------------------------------------------------------

@router.get("/admin/reset-preview")
async def reset_preview(x_admin_token: Optional[str] = Header(default=None), session: AsyncSession = Depends(get_async_session)):
    _require_admin(x_admin_token)

    users = await get_pvp_leaderboard_top(session, limit=5)
    sample = [
        {
            "user_id": u.id,
            "telegram_id": int(u.telegram_id),
            "pvp_victories": int(getattr(u, "pvp_victories", 0) or 0),
            "pvp_best_result": int(getattr(u, "pvp_best_result", 0) or 0),
        }
        for u in users
    ]

    return {"ok": True, "top_sample": sample}


@router.post("/admin/reset-week")
async def reset_week(x_admin_token: Optional[str] = Header(default=None), session: AsyncSession = Depends(get_async_session)):
    _require_admin(x_admin_token)

    try:
        affected = await reset_weekly_pvp_victories_for_all(session)
        await session.commit()
        return {"ok": True, "reset": True, "affected_rows": affected}
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail={"code": "RESET_FAILED", "message": str(e)})

