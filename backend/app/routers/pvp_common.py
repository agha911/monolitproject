# app/routers/pvp_common.py

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Any, Dict

import requests
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.models.user import User
from app.models.pvp_models import PvpInvite, PvpQueue, PvpSession
from app.crud.crud_pvp import (
    get_pvp_leaderboard_top,
    get_pvp_rank_for_user,
    list_recent_pvp_matches,
    list_recent_challenge_matches,
)

router = APIRouter(prefix="/api/pvp", tags=["pvp"])

PVP_DEFAULT_STAKE = 50000
PVP_MATCH_DURATION_SEC = 30
PVP_SESSION_TTL_SEC = 60  # если не финишнули — станет expired
PVP_INVITE_TTL_SEC = 600  # 10 минут
PVP_QUEUE_TTL_SEC = 120   # 2 минуты
CHALLENGE_DAILY_LIMIT = 5

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

try:
    from app.main import referral_cache  # type: ignore
except Exception:
    referral_cache = None  # pragma: no cover


# -----------------------------------------------------------------------------
# Schemas (общие)
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



class LiveSubmitRequest(BaseModel):
    telegram_id: int
    match_token: str
    my_clicks: int = Field(ge=0)


# -----------------------------------------------------------------------------
# Helpers (общие)
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
# Routes: общие
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
    me_user = await _ensure_registered_user(session, telegram_id)
    matches = await list_recent_pvp_matches(session, user_id=me_user.id, limit=20)
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
    me_user = await _ensure_registered_user(session, telegram_id)
    matches = await list_recent_challenge_matches(session, challenger_id=me_user.id, limit=20)
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


@router.post("/admin/reset-weekly")
async def admin_reset_weekly(
    secret_key: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_async_session),
):
    admin_key = os.getenv("PVP_ADMIN_KEY", "")
    if not admin_key or secret_key != admin_key:
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Invalid admin key"})

    async with session.begin():
        await session.execute(
            User.__table__.update().values(pvp_victories=0)  # type: ignore
        )
        return {"ok": True, "message": "Weekly victories reset done"}
