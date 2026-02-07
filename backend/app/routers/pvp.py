# app/routers/pvp.py
# PvP / Challenge router (в стиле challenge.py)
# ВАЖНО: этот файл использует таблицы pvp_invites и pvp_queue (см. SQL в комментариях ниже)

from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from sqlalchemy import select, desc, func, and_, or_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.models.user import User
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


# -----------------------------------------------------------------------------
# REQUIRED TABLES (create manually once)
# -----------------------------------------------------------------------------
# 1) pvp_invites
# CREATE TABLE IF NOT EXISTS pvp_invites (
#   id SERIAL PRIMARY KEY,
#   code TEXT NOT NULL UNIQUE,
#   creator_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
#   opponent_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
#   stake INTEGER NOT NULL DEFAULT 50000,
#   status TEXT NOT NULL DEFAULT 'created', -- created|accepted|cancelled|expired
#   created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
#   accepted_at TIMESTAMPTZ NULL,
#   cancelled_at TIMESTAMPTZ NULL,
#   expires_at TIMESTAMPTZ NULL
# );
# CREATE INDEX IF NOT EXISTS ix_pvp_invites_creator ON pvp_invites(creator_user_id);
# CREATE INDEX IF NOT EXISTS ix_pvp_invites_status  ON pvp_invites(status);
# CREATE INDEX IF NOT EXISTS ix_pvp_invites_created ON pvp_invites(created_at);
#
# 2) pvp_queue
# CREATE TABLE IF NOT EXISTS pvp_queue (
#   id SERIAL PRIMARY KEY,
#   user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
#   stake INTEGER NOT NULL DEFAULT 50000,
#   status TEXT NOT NULL DEFAULT 'waiting', -- waiting|matched|left|expired
#   matched_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
#   match_token TEXT NULL,
#   created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
#   updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
# );
# CREATE INDEX IF NOT EXISTS ix_pvp_queue_status_created ON pvp_queue(status, created_at);
# -----------------------------------------------------------------------------


# ====== Конфиг (хардкодим в одном месте, фронт читает отсюда) ======

PVP_ENABLED = True
PVP_DEFAULT_STAKE = 50000
PVP_MATCH_DURATION_SEC = 30
PVP_MULTITOUCH_LIMIT = 2
CHALLENGE_DAILY_LIMIT_DEFAULT = 5
CHALLENGE_RANGE_PCT_DEFAULT = 0.15

# админ-токен для reset (задай в Render env: PVP_ADMIN_TOKEN=...)
PVP_ADMIN_TOKEN = os.getenv("PVP_ADMIN_TOKEN", "")


# ====== схемы запросов ======

class LiveFinishRequest(BaseModel):
    telegram_id: int  # инициатор (player1)
    opponent_telegram_id: int  # player2
    player1_clicks: int = Field(ge=0)
    player2_clicks: int = Field(ge=0)
    stake: int = Field(default=PVP_DEFAULT_STAKE, ge=0)


class ChallengeRunRequest(BaseModel):
    telegram_id: int  # challenger
    opponent_telegram_id: int
    challenger_clicks: int = Field(ge=0)
    daily_limit: int = Field(default=CHALLENGE_DAILY_LIMIT_DEFAULT, ge=1, le=50)


class InviteCreateRequest(BaseModel):
    telegram_id: int
    stake: int = Field(default=PVP_DEFAULT_STAKE, ge=0)
    ttl_seconds: int = Field(default=3600, ge=60, le=86400)  # 1 час по умолчанию


class InviteAcceptRequest(BaseModel):
    telegram_id: int
    invite_code: str = Field(min_length=6, max_length=64)


class InviteCancelRequest(BaseModel):
    telegram_id: int
    invite_code: str = Field(min_length=6, max_length=64)


class MatchmakingJoinRequest(BaseModel):
    telegram_id: int
    stake: int = Field(default=PVP_DEFAULT_STAKE, ge=0)
    ttl_seconds: int = Field(default=120, ge=10, le=3600)  # очередь живёт 2 минуты по умолчанию


class MatchmakingLeaveRequest(BaseModel):
    telegram_id: int


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
# 1) Existing endpoints (Live finish / Challenge run)
# -----------------------------------------------------------------------------

@router.post("/live/finish")
async def live_finish(body: LiveFinishRequest, session: AsyncSession = Depends(get_async_session)):
    """
    Финализировать PvP Live матч (1v1).
    Денежная единица: total_xp.
    """
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
            "winner_id": result.winner_id,  # это user.id (не telegram_id)
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
    """
    Запустить Challenge:
    - лимит 5/день (по умолчанию)
    - победа: +1 victory
    - поражение: без изменений
    """
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
        items.append({
            "user_id": u.id,
            "telegram_id": int(u.telegram_id),
            "username": u.username,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "pvp_victories": int(getattr(u, "pvp_victories", 0) or 0),
            "pvp_best_result": int(getattr(u, "pvp_best_result", 0) or 0),
            "total_xp": int(getattr(u, "total_xp", 0) or 0),
        })

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
# 3) Challenge status + opponent matchmaking
# -----------------------------------------------------------------------------

@router.get("/challenge/status")
async def challenge_status(telegram_id: int, daily_limit: int = CHALLENGE_DAILY_LIMIT_DEFAULT,
                           session: AsyncSession = Depends(get_async_session)):
    user = await get_user(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    attempts_today = await count_today_challenge_attempts(session, challenger_id=user.id)
    start, end = baku_day_bounds()  # TZ Baku
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
    """
    Подбор оппонента по диапазону best_result ± pct.
    """
    me_user = await get_user(session, telegram_id)
    if not me_user:
        raise HTTPException(status_code=404, detail="User not found")

    my_best = int(getattr(me_user, "pvp_best_result", 0) or 0)
    low, high = calc_best_result_range(best_result=my_best, pct=float(pct), min_floor=0)

    # 1) пробуем в узком диапазоне
    q = (
        select(User)
        .where(User.id != me_user.id)
        .where(User.pvp_best_result >= low)
        .where(User.pvp_best_result <= high)
        .order_by(func.random())
        .limit(1)
    )
    res = await session.execute(q)
    opp = res.scalar_one_or_none()

    # 2) fallback: расширяем диапазон в 2 раза
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
        res2 = await session.execute(q2)
        opp = res2.scalar_one_or_none()

    # 3) последний fallback: любой пользователь с best_result > 0
    if not opp:
        q3 = (
            select(User)
            .where(User.id != me_user.id)
            .where(User.pvp_best_result >= 0)
            .order_by(func.random())
            .limit(1)
        )
        res3 = await session.execute(q3)
        opp = res3.scalar_one_or_none()

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
async def live_history(telegram_id: int, limit: int = 20, offset: int = 0, session: AsyncSession = Depends(get_async_session)):
    user = await get_user(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    matches = await list_recent_pvp_matches_for_user(session, user_id=user.id, limit=limit, offset=offset)

    items: List[Dict[str, Any]] = []
    for m in matches:
        items.append({
            "id": m.id,
            "player1_id": m.player1_id,
            "player2_id": m.player2_id,
            "player1_clicks": m.player1_clicks,
            "player2_clicks": m.player2_clicks,
            "stake": m.stake,
            "winner_id": m.winner_id,
            "is_draw": m.is_draw,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        })
    return {"ok": True, "items": items}


@router.get("/challenge/history")
async def challenge_history(telegram_id: int, limit: int = 20, offset: int = 0, session: AsyncSession = Depends(get_async_session)):
    user = await get_user(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    matches = await list_recent_challenge_matches_for_user(session, user_id=user.id, limit=limit, offset=offset)

    items: List[Dict[str, Any]] = []
    for m in matches:
        items.append({
            "id": m.id,
            "challenger_id": m.challenger_id,
            "opponent_id": m.opponent_id,
            "challenger_clicks": m.challenger_clicks,
            "opponent_best_result": m.opponent_best_result,
            "is_win": m.is_win,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        })
    return {"ok": True, "items": items}


# -----------------------------------------------------------------------------
# 5) Invite system (create / status / accept / cancel)
# -----------------------------------------------------------------------------

def _gen_invite_code() -> str:
    return secrets.token_urlsafe(8).replace("-", "").replace("_", "")


@router.post("/invite/create")
async def invite_create(body: InviteCreateRequest, session: AsyncSession = Depends(get_async_session)):
    creator = await get_user(session, body.telegram_id)
    if not creator:
        raise HTTPException(status_code=404, detail="User not found")

    # проверка баланса на ставку
    if body.stake > 0 and int(getattr(creator, "total_xp", 0) or 0) < body.stake:
        raise HTTPException(status_code=409, detail={"code": "INSUFFICIENT_COINS", "message": "Not enough coins for stake"})

    code = _gen_invite_code()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=body.ttl_seconds)

    try:
        await session.execute(
            text("""
                INSERT INTO pvp_invites (code, creator_user_id, stake, status, created_at, expires_at)
                VALUES (:code, :creator_user_id, :stake, 'created', now(), :expires_at)
            """),
            {"code": code, "creator_user_id": creator.id, "stake": body.stake, "expires_at": expires_at},
        )
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail={"code": "INVITE_CREATE_FAILED", "message": str(e)})

    # deep link: ты сам подставишь bot username на фронте/конфиге
    return {
        "ok": True,
        "invite_code": code,
        "stake": body.stake,
        "expires_at": expires_at.isoformat(),
        "start_param": f"pvp_{code}",
    }


@router.get("/invite/status")
async def invite_status(invite_code: str, session: AsyncSession = Depends(get_async_session)):
    res = await session.execute(
        text("""
            SELECT code, creator_user_id, opponent_user_id, stake, status, created_at, accepted_at, cancelled_at, expires_at
            FROM pvp_invites
            WHERE code = :code
            LIMIT 1
        """),
        {"code": invite_code},
    )
    row = res.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail={"code": "INVITE_NOT_FOUND", "message": "Invite not found"})

    # если истёк — помечаем expired (best effort)
    if row["expires_at"] and row["status"] == "created":
        try:
            exp = row["expires_at"]
            if isinstance(exp, str):
                # обычно не будет строкой, но на всякий
                exp_dt = datetime.fromisoformat(exp)
            else:
                exp_dt = exp
            if exp_dt <= datetime.now(timezone.utc):
                await session.execute(
                    text("UPDATE pvp_invites SET status='expired' WHERE code=:code AND status='created'"),
                    {"code": invite_code},
                )
                await session.commit()
                row = dict(row)
                row["status"] = "expired"
        except Exception:
            await session.rollback()

    return {"ok": True, "invite": dict(row)}


@router.post("/invite/cancel")
async def invite_cancel(body: InviteCancelRequest, session: AsyncSession = Depends(get_async_session)):
    user = await get_user(session, body.telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        res = await session.execute(
            text("""
                UPDATE pvp_invites
                SET status='cancelled', cancelled_at=now()
                WHERE code=:code
                  AND creator_user_id=:creator_user_id
                  AND status='created'
                RETURNING code, status
            """),
            {"code": body.invite_code, "creator_user_id": user.id},
        )
        row = res.mappings().first()
        if not row:
            await session.rollback()
            raise HTTPException(status_code=409, detail={"code": "INVITE_NOT_CANCELLABLE", "message": "Invite not found or already accepted/cancelled/expired"})
        await session.commit()
        return {"ok": True, "invite_code": body.invite_code, "status": row["status"]}
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail={"code": "INVITE_CANCEL_FAILED", "message": str(e)})


@router.post("/invite/accept")
async def invite_accept(body: InviteAcceptRequest, session: AsyncSession = Depends(get_async_session)):
    """
    Онбординг через invite:
    - если пользователь новый (нет в users) -> создаём и начисляем 50k total_xp
    - если монет нет -> отказ (учитываем правило "если монет нет — участие недоступно")
    """
    # 1) получаем / создаём пользователя
    user = await get_user(session, body.telegram_id)
    if not user:
        # авто-онбординг: создаём пользователя + 50k
        user = User(telegram_id=body.telegram_id, total_xp=PVP_DEFAULT_STAKE)
        session.add(user)
        await session.flush()  # получим user.id

    # 2) читаем invite и блокируем строку
    try:
        res = await session.execute(
            text("""
                SELECT id, creator_user_id, opponent_user_id, stake, status, expires_at
                FROM pvp_invites
                WHERE code = :code
                FOR UPDATE
            """),
            {"code": body.invite_code},
        )
        inv = res.mappings().first()
        if not inv:
            await session.rollback()
            raise HTTPException(status_code=404, detail={"code": "INVITE_NOT_FOUND", "message": "Invite not found"})

        if inv["status"] != "created":
            await session.rollback()
            raise HTTPException(status_code=409, detail={"code": "INVITE_NOT_ACTIVE", "message": f"Invite status = {inv['status']}"})

        if inv["expires_at"] and inv["expires_at"] <= datetime.now(timezone.utc):
            await session.execute(
                text("UPDATE pvp_invites SET status='expired' WHERE id=:id AND status='created'"),
                {"id": inv["id"]},
            )
            await session.commit()
            raise HTTPException(status_code=409, detail={"code": "INVITE_EXPIRED", "message": "Invite expired"})

        stake = int(inv["stake"] or 0)

        # 3) проверка баланса у принимающего
        if stake > 0 and int(getattr(user, "total_xp", 0) or 0) < stake:
            await session.rollback()
            raise HTTPException(status_code=409, detail={"code": "INSUFFICIENT_COINS", "message": "Not enough coins to accept stake"})

        # 4) проставляем opponent и accepted
        await session.execute(
            text("""
                UPDATE pvp_invites
                SET opponent_user_id=:opponent_user_id, status='accepted', accepted_at=now()
                WHERE id=:id AND status='created'
            """),
            {"opponent_user_id": user.id, "id": inv["id"]},
        )
        await session.commit()

        return {
            "ok": True,
            "invite_code": body.invite_code,
            "stake": stake,
            "creator_user_id": inv["creator_user_id"],
            "opponent_user_id": user.id,
            "match_duration_sec": PVP_MATCH_DURATION_SEC,
        }
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail={"code": "INVITE_ACCEPT_FAILED", "message": str(e)})


# -----------------------------------------------------------------------------
# 6) Random matchmaking via DB queue (join / poll / leave)
# -----------------------------------------------------------------------------

@router.post("/matchmaking/join")
async def matchmaking_join(body: MatchmakingJoinRequest, session: AsyncSession = Depends(get_async_session)):
    user = await get_user(session, body.telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # проверка баланса (если ставка)
    if body.stake > 0 and int(getattr(user, "total_xp", 0) or 0) < body.stake:
        raise HTTPException(status_code=409, detail={"code": "INSUFFICIENT_COINS", "message": "Not enough coins for stake"})

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=body.ttl_seconds)

    try:
        # upsert-подобное поведение: если уже waiting — обновим stake/updated_at
        await session.execute(
            text("""
                INSERT INTO pvp_queue (user_id, stake, status, created_at, updated_at)
                VALUES (:user_id, :stake, 'waiting', now(), now())
                ON CONFLICT (user_id)
                DO UPDATE SET stake=EXCLUDED.stake, status='waiting', matched_user_id=NULL, match_token=NULL, updated_at=now()
            """),
            {"user_id": user.id, "stake": body.stake},
        )
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
        await session.execute(
            text("DELETE FROM pvp_queue WHERE user_id=:user_id AND status='waiting'"),
            {"user_id": user.id},
        )
        await session.commit()
        return {"ok": True, "status": "left"}
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail={"code": "MATCHMAKING_LEAVE_FAILED", "message": str(e)})


@router.post("/matchmaking/poll")
async def matchmaking_poll(telegram_id: int, session: AsyncSession = Depends(get_async_session)):
    """
    Поллинг:
    - если уже matched -> возвращаем opponent + match_token
    - если waiting -> пытаемся "сматчить" с другим waiting (FOR UPDATE SKIP LOCKED)
    """
    me_user = await get_user(session, telegram_id)
    if not me_user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        # 1) если у меня уже есть matched
        res0 = await session.execute(
            text("""
                SELECT user_id, stake, status, matched_user_id, match_token
                FROM pvp_queue
                WHERE user_id=:me_id
                LIMIT 1
            """),
            {"me_id": me_user.id},
        )
        me_row = res0.mappings().first()
        if not me_row:
            # не в очереди
            return {"ok": True, "status": "not_in_queue"}

        if me_row["status"] == "matched" and me_row["matched_user_id"] and me_row["match_token"]:
            opp_id = int(me_row["matched_user_id"])
            resu = await session.execute(select(User).where(User.id == opp_id))
            opp = resu.scalar_one_or_none()
            return {
                "ok": True,
                "status": "matched",
                "stake": int(me_row["stake"] or 0),
                "match_token": me_row["match_token"],
                "opponent": {
                    "user_id": opp_id,
                    "telegram_id": int(opp.telegram_id) if opp else None,
                    "username": opp.username if opp else None,
                    "first_name": opp.first_name if opp else None,
                    "last_name": opp.last_name if opp else None,
                },
                "match_duration_sec": PVP_MATCH_DURATION_SEC,
            }

        if me_row["status"] != "waiting":
            return {"ok": True, "status": me_row["status"]}

        # 2) я waiting -> пытаемся найти другого waiting
        # блокируем кандидата, чтобы параллельные poll не схватили его же
        res1 = await session.execute(
            text("""
                SELECT id, user_id, stake
                FROM pvp_queue
                WHERE status='waiting'
                  AND user_id <> :me_id
                ORDER BY created_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            """),
            {"me_id": me_user.id},
        )
        cand = res1.mappings().first()
        if not cand:
            await session.commit()
            return {"ok": True, "status": "waiting"}

        # 3) матчим меня и кандидата
        match_token = secrets.token_urlsafe(12)

        # читаем мою строку FOR UPDATE
        res_me_lock = await session.execute(
            text("""
                SELECT id, stake
                FROM pvp_queue
                WHERE user_id=:me_id AND status='waiting'
                FOR UPDATE
            """),
            {"me_id": me_user.id},
        )
        me_locked = res_me_lock.mappings().first()
        if not me_locked:
            # я уже не waiting (кто-то удалил/сматчил)
            await session.commit()
            return {"ok": True, "status": "waiting"}

        # ставка: берём мою (или можно max/мин — решишь). Сейчас: используем мою.
        stake = int(me_locked["stake"] or 0)

        await session.execute(
            text("""
                UPDATE pvp_queue
                SET status='matched', matched_user_id=:opp_id, match_token=:token, updated_at=now()
                WHERE user_id=:me_id AND status='waiting'
            """),
            {"opp_id": int(cand["user_id"]), "token": match_token, "me_id": me_user.id},
        )
        await session.execute(
            text("""
                UPDATE pvp_queue
                SET status='matched', matched_user_id=:me_id, match_token=:token, updated_at=now()
                WHERE user_id=:opp_id AND status='waiting'
            """),
            {"me_id": me_user.id, "token": match_token, "opp_id": int(cand["user_id"])},
        )

        # отдаём opponent
        resu = await session.execute(select(User).where(User.id == int(cand["user_id"])))
        opp = resu.scalar_one_or_none()

        await session.commit()

        return {
            "ok": True,
            "status": "matched",
            "stake": stake,
            "match_token": match_token,
            "opponent": {
                "user_id": int(cand["user_id"]),
                "telegram_id": int(opp.telegram_id) if opp else None,
                "username": opp.username if opp else None,
                "first_name": opp.first_name if opp else None,
                "last_name": opp.last_name if opp else None,
            },
            "match_duration_sec": PVP_MATCH_DURATION_SEC,
        }

    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail={"code": "MATCHMAKING_POLL_FAILED", "message": str(e)})


# -----------------------------------------------------------------------------
# 7) Weekly reset admin
# -----------------------------------------------------------------------------

def _require_admin(x_admin_token: Optional[str]) -> None:
    if not PVP_ADMIN_TOKEN:
        # если токен не задан, лучше запретить
        raise HTTPException(status_code=403, detail={"code": "ADMIN_DISABLED", "message": "PVP_ADMIN_TOKEN not set"})
    if not x_admin_token or x_admin_token != PVP_ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Invalid admin token"})


@router.get("/admin/reset-preview")
async def reset_preview(x_admin_token: Optional[str] = Header(default=None), session: AsyncSession = Depends(get_async_session)):
    _require_admin(x_admin_token)

    # просто покажем топ-5 до сброса
    users = await get_pvp_leaderboard_top(session, limit=5)
    sample = [{
        "user_id": u.id,
        "telegram_id": int(u.telegram_id),
        "pvp_victories": int(getattr(u, "pvp_victories", 0) or 0),
        "pvp_best_result": int(getattr(u, "pvp_best_result", 0) or 0),
    } for u in users]

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
