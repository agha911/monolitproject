# app/routers/pvp_challenge.py

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.models.user import User
from app.helpers.pvp_helpers import calc_best_result_range
from app.crud.crud_pvp import count_today_challenge_attempts
from app.services.pvp_service import (
    run_challenge,
    ChallengeLimitExceeded,
    InvalidPayload,
)

from app.routers.pvp_common import (
    CHALLENGE_DAILY_LIMIT,
    ChallengeRunRequest,
    _cleanup_expired,
    _ensure_registered_user,
)

router = APIRouter(prefix="/api/pvp", tags=["pvp"])


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
    me_user = await _ensure_registered_user(session, telegram_id)
    attempts_today = await count_today_challenge_attempts(session, challenger_id=me_user.id)
    return {"ok": True, "attempts_today": attempts_today, "limit": CHALLENGE_DAILY_LIMIT}


@router.get("/challenge/opponent")
async def challenge_pick_opponent(telegram_id: int, session: AsyncSession = Depends(get_async_session)):
    me_user = await _ensure_registered_user(session, telegram_id)
    my_best = int(getattr(me_user, "pvp_best_result", 0) or 0)

    low, high = calc_best_result_range(my_best)

    q = (
        select(User)
        .where(User.id != me_user.id)
        .where(func.coalesce(User.pvp_best_result, 0).between(low, high))
        .order_by(func.random())
        .limit(1)
    )
    opp = (await session.execute(q)).scalar_one_or_none()
    if not opp:
        opp = (await session.execute(select(User).where(User.id != me_user.id).order_by(func.random()).limit(1))).scalar_one_or_none()

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
