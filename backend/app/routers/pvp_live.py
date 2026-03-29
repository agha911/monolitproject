# app/routers/pvp_live.py

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import get_async_session
from app.models.user import User
from app.models.pvp_models import PvpInvite, PvpQueue, PvpSession, PvpMatch
from app.services.pvp_service import (
    finish_live_pvp_session,
    InsufficientCoins,
    InvalidPayload,
    SessionNotFound,
    SessionNotActive,
    SessionExpired,
)

from app.routers.pvp_common import (
    PVP_DEFAULT_STAKE,
    PVP_MATCH_DURATION_SEC,
    PVP_SESSION_TTL_SEC,
    PVP_INVITE_TTL_SEC,
    PVP_QUEUE_TTL_SEC,
    InviteCreateRequest,
    InviteAcceptRequest,
    InviteCancelRequest,
    MatchmakingJoinRequest,
    MatchmakingLeaveRequest,
    LiveFinishRequest,
    LiveSubmitRequest,
    _cleanup_expired,
    _ensure_registered_user,
    _gen_invite_code,
    _gen_match_token,
    _user_public,
)
from app.helpers.pvp_helpers import review_telemetry
from app.models.pvp_anticheat_models import PvpLiveTelemetry
from app.crud.crud_pvp import (
    upsert_live_telemetry,
    get_live_telemetry_map,
    create_cheat_events_from_flags,
)
router = APIRouter(prefix="/api/pvp", tags=["pvp"])


@router.post("/live/finish")
async def live_finish(body: LiveFinishRequest, session: AsyncSession = Depends(get_async_session)):
    raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Endpoint not available"})
    """
    OLD debug endpoint (kept for tests):
    requester sends both clicks. Frontend should NOT use it in production.
    """
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


@router.post("/live/submit")
async def live_submit(body: LiveSubmitRequest, session: AsyncSession = Depends(get_async_session)):
    """
    PRODUCTION Live PvP:
    - each player submits ONLY their clicks
    - second submit triggers finalize
    """
    async with session.begin():
        await _cleanup_expired(session)
        me = await _ensure_registered_user(session, body.telegram_id)

        sess = (
            (await session.execute(
                select(PvpSession).where(PvpSession.match_token == body.match_token).with_for_update()
            ))
            .scalar_one_or_none()
        )
        if not sess:
            raise HTTPException(status_code=404, detail={"code": "SESSION_NOT_FOUND", "message": "Match session not found"})

        now = datetime.now(timezone.utc)

        if sess.expires_at and sess.expires_at < now:
            sess.status = "expired"
            await session.flush()
            raise HTTPException(status_code=409, detail={"code": "SESSION_EXPIRED", "message": "Match session expired"})

        if sess.status != "active":
            raise HTTPException(status_code=409, detail={"code": "SESSION_NOT_ACTIVE", "message": f"Session is not active: {sess.status}"})

        players = {int(sess.player1_id), int(sess.player2_id)}
        if int(me.id) not in players:
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Not a participant"})

        # save my clicks
        telemetry_dict = body.telemetry.model_dump(exclude_none=True) if body.telemetry else {}
        telemetry_dict["reported_clicks"] = int(body.my_clicks)

        verdict = review_telemetry(
            reported_clicks=int(body.my_clicks),
            telemetry=body.telemetry,
            server_started_at=(sess.created_at or now),
            server_finished_at=now,
        )

        player_slot = "player1" if int(me.id) == int(sess.player1_id) else "player2"

        if player_slot == "player1":
            if sess.player1_reported_clicks is not None:
                raise HTTPException(status_code=409, detail={"code": "ALREADY_SUBMITTED", "message": "You already submitted"})
            sess.player1_reported_clicks = int(body.my_clicks)
            sess.player1_reported_at = now
        else:
            if sess.player2_reported_clicks is not None:
                raise HTTPException(status_code=409, detail={"code": "ALREADY_SUBMITTED", "message": "You already submitted"})
            sess.player2_reported_clicks = int(body.my_clicks)
            sess.player2_reported_at = now

        tel = await upsert_live_telemetry(
            session,
            session_id=int(sess.id),
            match_token=sess.match_token,
            user_id=int(me.id),
            player_slot=player_slot,
            payload=telemetry_dict,
            verdict=verdict,
        )

        if verdict.flags:
            await create_cheat_events_from_flags(
                session,
                mode="live",
                user_id=int(me.id),
                flags=list(verdict.flags),
                reason=verdict.reason,
                session_id=int(sess.id),
                details_json={
                    "reported_clicks": int(body.my_clicks),
                    "validated_clicks": int(verdict.validated_clicks),
                    "score": int(verdict.suspicion_score),
                },
            )

        await session.flush()

        p1_done = sess.player1_reported_clicks is not None
        p2_done = sess.player2_reported_clicks is not None

        if p1_done and p2_done:
            opponent_user_id = int(sess.player2_id) if int(me.id) == int(sess.player1_id) else int(sess.player1_id)

            tel_map = await get_live_telemetry_map(session, session_id=int(sess.id))
            p1_tel = tel_map.get(int(sess.player1_id))
            p2_tel = tel_map.get(int(sess.player2_id))

            if not p1_tel or not p2_tel:
                raise HTTPException(status_code=409, detail={"code": "TELEMETRY_MISSING", "message": "Telemetry not fully submitted"})

            if int(me.id) == int(sess.player1_id):
                opponent_clicks = int(p2_tel.validated_clicks or 0)
                my_clicks = int(p1_tel.validated_clicks or 0)
            else:
                opponent_clicks = int(p1_tel.validated_clicks or 0)
                my_clicks = int(p2_tel.validated_clicks or 0)

            try:
                res = await finish_live_pvp_session(
                    session,
                    match_token=sess.match_token,
                    requester_user_id=int(me.id),
                    opponent_user_id=opponent_user_id,
                    requester_clicks=my_clicks,
                    opponent_clicks=opponent_clicks,
                    stake_fixed=PVP_DEFAULT_STAKE,
                )
                p1_user = await session.get(User, int(sess.player1_id))
                p2_user = await session.get(User, int(sess.player2_id))
            except (SessionNotFound, SessionNotActive, SessionExpired) as e:
                raise HTTPException(status_code=409, detail={"code": getattr(e, "code", "PVP_SESSION_ERROR"), "message": str(e)})
            except InsufficientCoins as e:
                raise HTTPException(status_code=409, detail={"code": "INSUFFICIENT_COINS", "message": str(e)})
            except InvalidPayload as e:
                raise HTTPException(status_code=422, detail={"code": "INVALID_PAYLOAD", "message": str(e)})

            return {
                "ok": True,
                "status": "finished",
                "match_token": sess.match_token,
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
                "player1": _user_public(p1_user),
                "player2": _user_public(p2_user),
                "anti_cheat": {
                    "player1": {
                        "reported_clicks": int(p1_tel.reported_clicks),
                        "validated_clicks": int(p1_tel.validated_clicks),
                        "is_suspicious": bool(p1_tel.is_suspicious),
                        "confidence": float(p1_tel.confidence or 0),
                        "score": int(p1_tel.suspicion_score or 0),
                        "reason": p1_tel.reason,
                        "flags": p1_tel.flags_json or [],
                    },
                    "player2": {
                        "reported_clicks": int(p2_tel.reported_clicks),
                        "validated_clicks": int(p2_tel.validated_clicks),
                        "is_suspicious": bool(p2_tel.is_suspicious),
                        "confidence": float(p2_tel.confidence or 0),
                        "score": int(p2_tel.suspicion_score or 0),
                        "reason": p2_tel.reason,
                        "flags": p2_tel.flags_json or [],
                    },
                },
            }
        
        p1_user = await session.get(User, int(sess.player1_id))
        p2_user = await session.get(User, int(sess.player2_id))
        return {
            "ok": True,
            "status": "waiting",
            "match_token": sess.match_token,
            "expires_at": sess.expires_at.isoformat() if sess.expires_at else None,
            "player1_id": int(sess.player1_id),
            "player2_id": int(sess.player2_id),
            "player1": _user_public(p1_user),
            "player2": _user_public(p2_user),
            "submitted": {
                "player1": p1_done,
                "player2": p2_done,
            },
        }


@router.get("/live/status")
async def live_status(telegram_id: int, match_token: str, session: AsyncSession = Depends(get_async_session)):
    await _cleanup_expired(session)
    me = await _ensure_registered_user(session, telegram_id)

    sess = (
        (await session.execute(select(PvpSession).where(PvpSession.match_token == match_token).limit(1)))
        .scalar_one_or_none()
    )
    p1_user = await session.get(User, int(sess.player1_id))
    p2_user = await session.get(User, int(sess.player2_id))
    tel_map = await get_live_telemetry_map(session, session_id=int(sess.id))
    p1_tel = tel_map.get(int(sess.player1_id))
    p2_tel = tel_map.get(int(sess.player2_id))
    opponent_user = p2_user if int(me.id) == int(sess.player1_id) else p1_user
    if not sess:
        raise HTTPException(status_code=404, detail={"code": "SESSION_NOT_FOUND", "message": "Match session not found"})

    players = {int(sess.player1_id), int(sess.player2_id)}
    if int(me.id) not in players:
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Not a participant"})

    out = {
        "ok": True,
        "status": sess.status,
        "match_token": sess.match_token,
        "expires_at": sess.expires_at.isoformat() if sess.expires_at else None,
        "finished_at": sess.finished_at.isoformat() if sess.finished_at else None,
        "player1_id": int(sess.player1_id),
        "player2_id": int(sess.player2_id),
        "submitted": {
            "player1": sess.player1_reported_clicks is not None,
            "player2": sess.player2_reported_clicks is not None,
        },
        "match_id": int(sess.match_id) if sess.match_id else None,
        "player1": _user_public(p1_user),
        "player2": _user_public(p2_user),
        "opponent": _user_public(opponent_user),
        "anti_cheat": {
            "player1": {
                "reported_clicks": int(p1_tel.reported_clicks) if p1_tel else None,
                "validated_clicks": int(p1_tel.validated_clicks) if p1_tel else None,
                "is_suspicious": bool(p1_tel.is_suspicious) if p1_tel else None,
                "confidence": float(p1_tel.confidence or 0) if p1_tel else None,
                "score": int(p1_tel.suspicion_score or 0) if p1_tel else None,
                "reason": p1_tel.reason if p1_tel else None,
                "flags": p1_tel.flags_json if p1_tel else [],
            },
            "player2": {
                "reported_clicks": int(p2_tel.reported_clicks) if p2_tel else None,
                "validated_clicks": int(p2_tel.validated_clicks) if p2_tel else None,
                "is_suspicious": bool(p2_tel.is_suspicious) if p2_tel else None,
                "confidence": float(p2_tel.confidence or 0) if p2_tel else None,
                "score": int(p2_tel.suspicion_score or 0) if p2_tel else None,
                "reason": p2_tel.reason if p2_tel else None,
                "flags": p2_tel.flags_json if p2_tel else [],
            },
        },
    }

    if sess.status == "finished" and sess.match_id:
        m = (await session.execute(select(PvpMatch).where(PvpMatch.id == sess.match_id).limit(1))).scalar_one_or_none()
        if m:
            out["result"] = {
                "match_id": int(m.id),
                "winner_id": int(m.winner_id) if m.winner_id else None,
                "is_draw": bool(m.is_draw),
                "player1_id": int(m.player1_id),
                "player2_id": int(m.player2_id),
                "player1_clicks": int(m.player1_clicks),
                "player2_clicks": int(m.player2_clicks),
                "stake": int(m.stake),
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }

    return out


# -----------------------------------------------------------------------------
# Invites
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
            "match_duration_sec": PVP_MATCH_DURATION_SEC,
        }


@router.get("/invite/status")
async def invite_status(invite_code: str, session: AsyncSession = Depends(get_async_session)):
    await _cleanup_expired(session)

    inv = (await session.execute(select(PvpInvite).where(PvpInvite.code == invite_code))).scalar_one_or_none()
    if not inv:
        return {"ok": False, "message": "Invite not found"}

    match_token = None
    player1_id = None
    player2_id = None
    if inv.status == "accepted":
        sess = (
            (await session.execute(
                select(PvpSession)
                .where(PvpSession.invite_id == inv.id)
                .order_by(PvpSession.created_at.desc())
                .limit(1)
            ))
            .scalar_one_or_none()
        )
        if sess:
            match_token = sess.match_token
            player1_id = int(sess.player1_id)
            player2_id = int(sess.player2_id)
            

    return {
        "ok": True,
        "invite_code": inv.code,
        "status": inv.status,
        "match_token": match_token,
        "player1_id": player1_id,
        "player2_id": player2_id,
        "creator_user_id": inv.creator_user_id,
        "opponent_user_id": inv.opponent_user_id,
        "stake": inv.stake,
        "match_duration_sec": PVP_MATCH_DURATION_SEC,
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
            (await session.execute(
                select(PvpInvite).where(PvpInvite.code == body.invite_code)
            ))
            .scalar_one_or_none()
        )
        if not inv:
            raise HTTPException(status_code=404, detail={"code": "INVITE_NOT_FOUND", "message": "Invite not found"})

        if inv.status != "created":
            raise HTTPException(status_code=409, detail={"code": "INVITE_NOT_ACTIVE", "message": f"Invite status is {inv.status}"})

        if inv.creator_user_id == opponent.id:
            raise HTTPException(status_code=409, detail={"code": "INVITE_SELF", "message": "Can't accept your own invite"})

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

        "player1": _user_public(creator),
        "player2": _user_public(opponent),

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
# Matchmaking
# -----------------------------------------------------------------------------

@router.post("/matchmaking/join")
async def matchmaking_join(body: MatchmakingJoinRequest, session: AsyncSession = Depends(get_async_session)):
    async with session.begin():
        await _cleanup_expired(session)

        user = await _ensure_registered_user(session, body.telegram_id)

        if int(getattr(user, "total_xp", 0) or 0) < PVP_DEFAULT_STAKE:
            raise HTTPException(status_code=409, detail={"code": "INSUFFICIENT_COINS", "message": "Not enough coins for stake"})

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

        now = datetime.now(timezone.utc)

        me = await _ensure_registered_user(session, telegram_id)

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

        if my_q.status == "waiting" and my_q.expires_at and my_q.expires_at < now:
            my_q.status = "expired"
            await session.flush()
            return {"ok": True, "status": "expired"}

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
                    "match_token": sess.match_token,
                    "expires_at": sess.expires_at.isoformat() if sess.expires_at else None,
                    "stake": sess.stake,
                    "match_duration_sec": PVP_MATCH_DURATION_SEC,
                    "mode": "matchmaking",
                    "player1_id": int(sess.player1_id),
                    "player2_id": int(sess.player2_id),
                    "opponent_user_id": opponent_user_id,
                }

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

        opp_q = await session.get(PvpQueue, opp_q_id, with_for_update=True)
        if not opp_q:
            return {"ok": True, "status": "waiting"}

        if my_q.status != "waiting":
            return {"ok": True, "status": my_q.status}

        opponent = (
            await session.execute(select(User).where(User.id == opp_q.user_id).limit(1))
        ).scalar_one()

        if int(getattr(opponent, "total_xp", 0) or 0) < PVP_DEFAULT_STAKE:
            opp_q.status = "expired"
            await session.flush()
            return {"ok": True, "status": "waiting"}

        if int(getattr(me, "total_xp", 0) or 0) < PVP_DEFAULT_STAKE:
            my_q.status = "expired"
            await session.flush()
            return {"ok": True, "status": "expired", "message": "Not enough coins anymore"}

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
            "opponent_user_id": int(opponent.id),
        }
