# app/routers/pvp.py

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Any, Dict, List

import requests
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import get_async_session
from app.models.user import User
from app.models.pvp_models import PvpInvite, PvpQueue, PvpSession, PvpMatch, ChallengeMatch
from app.helpers.pvp_helpers import (
    az_now,
    az_day_bounds_utc,
    calc_best_result_range,
)
from app.crud.crud_pvp import (
    get_pvp_leaderboard_top,
    get_pvp_rank_for_user,
    list_recent_pvp_matches,
    list_recent_challenge_matches,
    count_today_challenge_attempts,
)
from app.services.pvp_service import (
    finish_live_pvp_session,
    run_challenge,
    InsufficientCoins,
    ChallengeLimitExceeded,
    InvalidPayload,
    SessionNotFound,
    SessionNotActive,
    SessionExpired,
)

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------

router = APIRouter(prefix="/api/pvp", tags=["pvp"])

PVP_DEFAULT_STAKE = 50000
PVP_MATCH_DURATION_SEC = 30
PVP_SESSION_TTL_SEC = 60  # на всякий случай: если не финишнули, станет expired
PVP_INVITE_TTL_SEC = 600  # 10 минут
PVP_QUEUE_TTL_SEC = 120   # 2 минуты
CHALLENGE_DAILY_LIMIT = 5

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# referral_cache ожидается в main (как у тебя уже сделано)
try:
    from app.main import referral_cache  # type: ignore
except Exception:
    referral_cache = None  # pragma: no cover


# -----------------------------------------------------------------------------
# Schemas
# -----------------------------------------------------------------------------

class ConfigOut(BaseModel):
    ok: bool = True
    stake: int
    match_duration_sec: int
    invite_ttl_sec: int
    queue_ttl_sec: int
    session_ttl_sec: int
    challenge_daily_limit: int


class InviteCreateRequest(BaseModel):
    telegram_id: int
    ttl_seconds: int = Field(default=PVP_INVITE_TTL_SEC, ge=30, le=86400)


class InviteAcceptRequest(BaseModel):
    telegram_id: int
    invite_code: str


class InviteCancelRequest(BaseModel):
    telegram_id: int
    invite_code: str


class MatchmakingJoinRequest(BaseModel):
    telegram_id: int


class MatchmakingLeaveRequest(BaseModel):
    telegram_id: int


class LiveFinishRequest(BaseModel):
    telegram_id: int
    match_token: str
    opponent_user_id: int
    my_clicks: int = Field(ge=0)
    opponent_clicks: int = Field(ge=0)


class ChallengeRunRequest(BaseModel):
    telegram_id: int
    opponent_user_id: int
    my_clicks: int = Field(ge=0)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _gen_invite_code() -> str:
    return secrets.token_urlsafe(8)


def _gen_match_token() -> str:
    return secrets.token_urlsafe(24)


def _tg_getchat(telegram_id: int) -> Dict[str, Any]:
    if not TELEGRAM_BOT_TOKEN:
        return {}
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getChat"
    try:
        r = requests.get(url, params={"chat_id": telegram_id}, timeout=6)
        data = r.json()
        if not data.get("ok"):
            return {}
        return data.get("result") or {}
    except Exception:
        return {}


async def _cleanup_expired(session: AsyncSession) -> None:
    """
    Best-effort cleanup без cron:
    - истёкшие invites: created -> expired
    - истёкшие queue: waiting -> expired
    - истёкшие sessions: active -> expired
    """
    now = datetime.now(timezone.utc)

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


async def _ensure_registered_user(session: AsyncSession, telegram_id: int) -> User:
    """
    "Стандартная регистрация" для PvP (аналог main.py, но без init_data):
    - Если user есть: дозаполняем username/first/last через Bot API.
      Если есть referral_cache и invited_by — можно начислять бонусы (как у тебя заведено).
    - Если нет: создаём user.
    """
    q = select(User).where(User.telegram_id == telegram_id)
    user = (await session.execute(q)).scalar_one_or_none()

    tg = _tg_getchat(telegram_id)
    username = tg.get("username")
    first_name = tg.get("first_name")
    last_name = tg.get("last_name")

    if user:
        changed = False
        if username and (getattr(user, "username", None) != username):
            user.username = username
            changed = True
        if first_name and (getattr(user, "first_name", None) != first_name):
            user.first_name = first_name
            changed = True
        if last_name and (getattr(user, "last_name", None) != last_name):
            user.last_name = last_name
            changed = True
        if changed:
            await session.flush()
        return user

    user = User(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
    )
    session.add(user)
    await session.flush()
    return user


# -----------------------------------------------------------------------------
# 1) Config
# -----------------------------------------------------------------------------

@router.get("/config", response_model=ConfigOut)
async def get_config() -> ConfigOut:
    return ConfigOut(
        stake=PVP_DEFAULT_STAKE,
        match_duration_sec=PVP_MATCH_DURATION_SEC,
        invite_ttl_sec=PVP_INVITE_TTL_SEC,
        queue_ttl_sec=PVP_QUEUE_TTL_SEC,
        session_ttl_sec=PVP_SESSION_TTL_SEC,
        challenge_daily_limit=CHALLENGE_DAILY_LIMIT,
    )


# -----------------------------------------------------------------------------
# 2) Leaderboard / Me / History
# -----------------------------------------------------------------------------

@router.get("/leaderboard")
async def leaderboard(session: AsyncSession = Depends(get_async_session)):
    top = await get_pvp_leaderboard_top(session, limit=10)
    items = []
    for u in top:
        items.append(
            {
                "user_id": u.id,
                "telegram_id": u.telegram_id,
                "username": getattr(u, "username", None),
                "first_name": getattr(u, "first_name", None),
                "victories": int(getattr(u, "pvp_victories", 0) or 0),
                "best_result": int(getattr(u, "pvp_best_result", 0) or 0),
            }
        )
    return {"ok": True, "items": items}


@router.get("/me")
async def me(telegram_id: int, session: AsyncSession = Depends(get_async_session)):
    user = await _ensure_registered_user(session, telegram_id)
    rank = await get_pvp_rank_for_user(session, user_id=user.id)
    return {
        "ok": True,
        "user_id": user.id,
        "telegram_id": user.telegram_id,
        "username": getattr(user, "username", None),
        "first_name": getattr(user, "first_name", None),
        "victories": int(getattr(user, "pvp_victories", 0) or 0),
        "best_result": int(getattr(user, "pvp_best_result", 0) or 0),
        "rank": rank,
    }


@router.get("/live/history")
async def live_history(telegram_id: int, session: AsyncSession = Depends(get_async_session)):
    me = await _ensure_registered_user(session, telegram_id)
    matches = await list_recent_pvp_matches(session, user_id=me.id, limit=20)
    items = []
    for m in matches:
        items.append(
            {
                "id": m.id,
                "player1_id": m.player1_id,
                "player2_id": m.player2_id,
                "winner_id": m.winner_id,
                "is_draw": m.is_draw,
                "player1_clicks": m.player1_clicks,
                "player2_clicks": m.player2_clicks,
                "stake": m.stake,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
        )
    return {"ok": True, "items": items}


@router.get("/challenge/history")
async def challenge_history(telegram_id: int, session: AsyncSession = Depends(get_async_session)):
    me = await _ensure_registered_user(session, telegram_id)
    matches = await list_recent_challenge_matches(session, challenger_id=me.id, limit=20)
    items = []
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
# 3) Live finish
# -----------------------------------------------------------------------------

@router.post("/live/finish")
async def live_finish(body: LiveFinishRequest, session: AsyncSession = Depends(get_async_session)):
    async with session.begin():
        await _cleanup_expired(session)

        me = await _ensure_registered_user(session, body.telegram_id)

        try:
            res = await finish_live_pvp_session(
                session,
                match_token=body.match_token,
                requester_user_id=me.id,
                opponent_user_id=body.opponent_user_id,
                requester_clicks=body.my_clicks,
                opponent_clicks=body.opponent_clicks,
                stake_fixed=PVP_DEFAULT_STAKE,
            )
        except (SessionNotFound, SessionNotActive, SessionExpired) as e:
            raise HTTPException(status_code=409, detail={"code": getattr(e, "code", "PVP_SESSION_ERROR"), "message": str(e)})
        except InsufficientCoins as e:
            raise HTTPException(status_code=409, detail={"code": "INSUFFICIENT_COINS", "message": str(e)})
        except InvalidPayload as e:
            raise HTTPException(status_code=422, detail={"code": "INVALID_PAYLOAD", "message": str(e)})

        return {
            "ok": True,
            "match_id": res.match_id,
            "winner_id": res.winner_id,
            "is_draw": res.is_draw,
            "player1_id": res.player1_id,
            "player2_id": res.player2_id,
            "player1_clicks": res.player1_clicks,
            "player2_clicks": res.player2_clicks,
            "stake": res.stake,
            "player1_total_xp": res.player1_total_xp,
            "player2_total_xp": res.player2_total_xp,
        }


# -----------------------------------------------------------------------------
# 4) Challenge
# -----------------------------------------------------------------------------

@router.post("/challenge/run")
async def challenge_run(body: ChallengeRunRequest, session: AsyncSession = Depends(get_async_session)):
    async with session.begin():
        await _cleanup_expired(session)

        challenger = await _ensure_registered_user(session, body.telegram_id)

        try:
            res = await run_challenge(
                session,
                challenger_id=challenger.id,
                opponent_id=body.opponent_user_id,
                challenger_clicks=body.my_clicks,
                daily_limit=CHALLENGE_DAILY_LIMIT,
            )
        except ChallengeLimitExceeded as e:
            raise HTTPException(status_code=409, detail={"code": "CHALLENGE_LIMIT", "message": str(e)})
        except InvalidPayload as e:
            raise HTTPException(status_code=422, detail={"code": "INVALID_PAYLOAD", "message": str(e)})

        return {
            "ok": True,
            "match_id": res.match_id,
            "challenger_id": res.challenger_id,
            "opponent_id": res.opponent_id,
            "challenger_clicks": res.challenger_clicks,
            "opponent_best_result": res.opponent_best_result,
            "is_win": res.is_win,
            "victories_delta": res.victories_delta,
            "challenger_total_xp": res.challenger_total_xp,
            "challenger_best_result": res.challenger_best_result,
        }


@router.get("/challenge/status")
async def challenge_status(telegram_id: int, session: AsyncSession = Depends(get_async_session)):
    me = await _ensure_registered_user(session, telegram_id)
    attempts_today = await count_today_challenge_attempts(session, challenger_id=me.id)
    return {"ok": True, "attempts_today": attempts_today, "limit": CHALLENGE_DAILY_LIMIT}


@router.get("/challenge/opponent")
async def challenge_pick_opponent(telegram_id: int, session: AsyncSession = Depends(get_async_session)):
    """
    Подбор оппонента по диапазону best_result (best +/- %)
    """
    me = await _ensure_registered_user(session, telegram_id)
    my_best = int(getattr(me, "pvp_best_result", 0) or 0)

    low, high = calc_best_result_range(my_best)

    q = (
        select(User)
        .where(User.id != me.id)
        .where(func.coalesce(User.pvp_best_result, 0).between(low, high))
        .order_by(func.random())
        .limit(1)
    )
    opp = (await session.execute(q)).scalar_one_or_none()
    if not opp:
        # fallback: кто угодно
        opp = (await session.execute(select(User).where(User.id != me.id).order_by(func.random()).limit(1))).scalar_one_or_none()

    if not opp:
        return {"ok": False, "message": "No opponent found"}

    return {
        "ok": True,
        "opponent": {
            "user_id": opp.id,
            "telegram_id": opp.telegram_id,
            "username": getattr(opp, "username", None),
            "first_name": getattr(opp, "first_name", None),
            "best_result": int(getattr(opp, "pvp_best_result", 0) or 0),
            "victories": int(getattr(opp, "pvp_victories", 0) or 0),
        },
    }


# -----------------------------------------------------------------------------
# 5) Invites
# -----------------------------------------------------------------------------

@router.post("/invite/create")
async def invite_create(body: InviteCreateRequest, session: AsyncSession = Depends(get_async_session)):
    async with session.begin():
        await _cleanup_expired(session)

        creator = await _ensure_registered_user(session, body.telegram_id)

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

        return {
            "ok": True,
            "invite_code": code,
            "stake": PVP_DEFAULT_STAKE,
            "expires_at": expires_at.isoformat(),
            "start_param": f"pvp_{code}",
            "match_duration_sec": PVP_MATCH_DURATION_SEC,  # ✅ NEW (удобно сразу)
        }


@router.get("/invite/status")
async def invite_status(invite_code: str, session: AsyncSession = Depends(get_async_session)):
    await _cleanup_expired(session)

    inv = (await session.execute(select(PvpInvite).where(PvpInvite.code == invite_code))).scalar_one_or_none()
    if not inv:
        return {"ok": False, "message": "Invite not found"}

    return {
        "ok": True,
        "invite_code": inv.code,
        "status": inv.status,
        "creator_user_id": inv.creator_user_id,
        "opponent_user_id": inv.opponent_user_id,
        "stake": inv.stake,
        "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
        "accepted_at": inv.accepted_at.isoformat() if inv.accepted_at else None,
        "cancelled_at": inv.cancelled_at.isoformat() if inv.cancelled_at else None,
    }


@router.post("/invite/accept")
async def invite_accept(body: InviteAcceptRequest, session: AsyncSession = Depends(get_async_session)):
    async with session.begin():
        await _cleanup_expired(session)

        opponent = await _ensure_registered_user(session, body.telegram_id)

        inv = (
            (await session.execute(select(PvpInvite).where(PvpInvite.code == body.invite_code)))
            .scalar_one_or_none()
        )
        if not inv:
            raise HTTPException(status_code=404, detail={"code": "INVITE_NOT_FOUND", "message": "Invite not found"})

        if inv.status != "created":
            raise HTTPException(status_code=409, detail={"code": "INVITE_NOT_ACTIVE", "message": f"Invite status is {inv.status}"})

        if inv.creator_user_id == opponent.id:
            raise HTTPException(status_code=409, detail={"code": "INVITE_SELF", "message": "Can't accept your own invite"})

        # stake checks
        if int(getattr(opponent, "total_xp", 0) or 0) < PVP_DEFAULT_STAKE:
            raise HTTPException(status_code=409, detail={"code": "INSUFFICIENT_COINS", "message": "Not enough coins for stake"})

        creator = (await session.execute(select(User).where(User.id == inv.creator_user_id))).scalar_one()

        if int(getattr(creator, "total_xp", 0) or 0) < PVP_DEFAULT_STAKE:
            raise HTTPException(status_code=409, detail={"code": "CREATOR_INSUFFICIENT_COINS", "message": "Creator has not enough coins for stake"})

        inv.status = "accepted"
        inv.opponent_user_id = opponent.id
        inv.accepted_at = datetime.now(timezone.utc)

        match_token = _gen_match_token()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=PVP_SESSION_TTL_SEC)

        sess = PvpSession(
            match_token=match_token,
            player1_id=inv.creator_user_id,
            player2_id=opponent.id,
            stake=PVP_DEFAULT_STAKE,
            mode="invite",
            invite_id=inv.id,
            status="active",
            expires_at=expires_at,
        )
        session.add(sess)

        return {
            "ok": True,
            "match_token": match_token,
            "expires_at": expires_at.isoformat(),
            "stake": PVP_DEFAULT_STAKE,
            "match_duration_sec": PVP_MATCH_DURATION_SEC,
            "mode": "invite",
            "player1_id": int(sess.player1_id),
            "player2_id": int(sess.player2_id),
        }


@router.post("/invite/cancel")
async def invite_cancel(body: InviteCancelRequest, session: AsyncSession = Depends(get_async_session)):
    async with session.begin():
        await _cleanup_expired(session)

        user = await _ensure_registered_user(session, body.telegram_id)

        inv = (
            (await session.execute(select(PvpInvite).where(PvpInvite.code == body.invite_code)))
            .scalar_one_or_none()
        )
        if not inv:
            raise HTTPException(status_code=404, detail={"code": "INVITE_NOT_FOUND", "message": "Invite not found"})

        if inv.creator_user_id != user.id:
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Only creator can cancel invite"})

        if inv.status != "created":
            raise HTTPException(status_code=409, detail={"code": "INVITE_NOT_ACTIVE", "message": f"Invite status is {inv.status}"})

        inv.status = "cancelled"
        inv.cancelled_at = datetime.now(timezone.utc)

        return {"ok": True, "status": inv.status}


# -----------------------------------------------------------------------------
# 6) Matchmaking
# -----------------------------------------------------------------------------

@router.post("/matchmaking/join")
async def matchmaking_join(body: MatchmakingJoinRequest, session: AsyncSession = Depends(get_async_session)):
    async with session.begin():
        await _cleanup_expired(session)

        user = await _ensure_registered_user(session, body.telegram_id)

        if int(getattr(user, "total_xp", 0) or 0) < PVP_DEFAULT_STAKE:
            raise HTTPException(status_code=409, detail={"code": "INSUFFICIENT_COINS", "message": "Not enough coins for stake"})

        # upsert into queue
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=PVP_QUEUE_TTL_SEC)

        stmt = pg_insert(PvpQueue).values(
            user_id=user.id,
            stake=PVP_DEFAULT_STAKE,
            status="waiting",
            matched_user_id=None,
            match_token=None,
            expires_at=expires_at,
        )
        stmt = stmt.on_conflict_do_update(
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

        return {
            "ok": True,
            "status": "waiting",
            "expires_at": expires_at.isoformat(),
            "stake": PVP_DEFAULT_STAKE,
            "match_duration_sec": PVP_MATCH_DURATION_SEC,
        }


@router.post("/matchmaking/leave")
async def matchmaking_leave(body: MatchmakingLeaveRequest, session: AsyncSession = Depends(get_async_session)):
    async with session.begin():
        await _cleanup_expired(session)

        user = await _ensure_registered_user(session, body.telegram_id)

        q = (await session.execute(select(PvpQueue).where(PvpQueue.user_id == user.id))).scalar_one_or_none()
        if not q:
            return {"ok": True, "status": "not_in_queue"}

        q.status = "left"
        q.matched_user_id = None
        q.match_token = None
        q.expires_at = None
        await session.flush()

        return {"ok": True, "status": "left"}


@router.post("/matchmaking/poll")
async def matchmaking_poll(telegram_id: int, session: AsyncSession = Depends(get_async_session)):
    async with session.begin():
        await _cleanup_expired(session)

        me = await _ensure_registered_user(session, telegram_id)

        # 1) Берём ID моей очереди (без JOIN) и при необходимости лочим уже через session.get
        my_q_id = (
            await session.execute(
                select(PvpQueue.id).where(PvpQueue.user_id == me.id).limit(1)
            )
        ).scalar_one_or_none()

        if not my_q_id:
            return {"ok": True, "status": "not_in_queue"}

        my_q = await session.get(PvpQueue, my_q_id, with_for_update=True)
        if not my_q:
            return {"ok": True, "status": "not_in_queue"}

        # 2) Если уже matched — просто отдаём match_token (сессию тоже читаем без FOR UPDATE)
        if my_q.status == "matched" and my_q.match_token:
            sess = (
                await session.execute(
                    select(PvpSession).where(PvpSession.match_token == my_q.match_token).limit(1)
                )
            ).scalar_one_or_none()

             if sess:
                opponent_user_id = int(sess.player2_id) if int(sess.player1_id) == int(me.id) else int(sess.player1_id)
            
                return {
                        "ok": True,
                        "status": "matched",
                        "match_token": match_token,
                        "expires_at": expires_at.isoformat(),
                        "stake": PVP_DEFAULT_STAKE,
                        "match_duration_sec": PVP_MATCH_DURATION_SEC,
                        "mode": "matchmaking",
                        "player1_id": int(sess.player1_id),
                        "player2_id": int(sess.player2_id),
                        "opponent_user_id": int(opponent.id),  # <-- вот это добавь
                    }



        # 3) Ищем оппонента: ЛОЧИМ только pvp_queue.id (без JOIN) с SKIP LOCKED
        opp_q_id = (
            await session.execute(
                select(PvpQueue.id)
                .where(PvpQueue.status == "waiting")
                .where(PvpQueue.user_id != me.id)
                .order_by(PvpQueue.created_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
        ).scalar_one_or_none()

        if not opp_q_id:
            return {"ok": True, "status": my_q.status}

        # 4) Лочим строку оппонента отдельным session.get — без JOIN, без outer join проблем
        opp_q = await session.get(PvpQueue, opp_q_id, with_for_update=True)
        if not opp_q:
            return {"ok": True, "status": "waiting"}

        # 5) Проверяем, что я всё ещё waiting
        if my_q.status != "waiting":
            return {"ok": True, "status": my_q.status}

        # 6) Подтягиваем оппонента (можно без lock, но stake-check нужен)
        opponent = (
            await session.execute(select(User).where(User.id == opp_q.user_id).limit(1))
        ).scalar_one()

        # stake checks (оппонент мог потратить монеты)
        if int(getattr(opponent, "total_xp", 0) or 0) < PVP_DEFAULT_STAKE:
            opp_q.status = "expired"
            await session.flush()
            return {"ok": True, "status": "waiting"}

        if int(getattr(me, "total_xp", 0) or 0) < PVP_DEFAULT_STAKE:
            my_q.status = "expired"
            await session.flush()
            return {"ok": True, "status": "expired", "message": "Not enough coins anymore"}

        # 7) Матчим
        match_token = _gen_match_token()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=PVP_SESSION_TTL_SEC)

        my_q.status = "matched"
        my_q.matched_user_id = opponent.id
        my_q.match_token = match_token
        my_q.expires_at = None

        opp_q.status = "matched"
        opp_q.matched_user_id = me.id
        opp_q.match_token = match_token
        opp_q.expires_at = None

        # 8) Создаём session матча
        sess = PvpSession(
            match_token=match_token,
            player1_id=me.id,
            player2_id=opponent.id,
            stake=PVP_DEFAULT_STAKE,
            mode="matchmaking",
            invite_id=None,
            status="active",
            expires_at=expires_at,
        )
        session.add(sess)

        return {
            "ok": True,
            "status": "matched",
            "match_token": match_token,
            "expires_at": expires_at.isoformat(),
            "stake": PVP_DEFAULT_STAKE,
            "match_duration_sec": PVP_MATCH_DURATION_SEC,
            "mode": "matchmaking",
            "player1_id": int(sess.player1_id),
            "player2_id": int(sess.player2_id),
        }


# -----------------------------------------------------------------------------
# 7) Admin
# -----------------------------------------------------------------------------

@router.post("/admin/reset-weekly")
async def admin_reset_weekly(secret_key: Optional[str] = Header(default=None), session: AsyncSession = Depends(get_async_session)):
    """
    Простой "админ" эндпоинт: сброс victories раз в неделю.
    """
    admin_key = os.getenv("PVP_ADMIN_KEY", "")
    if not admin_key or secret_key != admin_key:
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Invalid admin key"})

    async with session.begin():
        # reset
        await session.execute(
            User.__table__.update().values(pvp_victories=0)  # type: ignore
        )
        return {"ok": True, "message": "Weekly victories reset done"}





