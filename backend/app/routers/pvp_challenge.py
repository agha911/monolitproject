# app/routers/pvp_challenge.py

from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.models.user import User
from app.helpers.pvp_helpers import calc_best_result_range

from app.crud.crud_pvp import (
    count_today_challenge_attempts,
    create_challenge_attempt,
    get_challenge_attempt_for_update,
    finish_challenge_attempt,
    expire_challenge_attempt,
)

from app.routers.pvp_common import (
    CHALLENGE_DAILY_LIMIT,
    PVP_MATCH_DURATION_SEC,
    _cleanup_expired,
    _ensure_registered_user,
)

router = APIRouter(prefix="/api/pvp", tags=["pvp"])


class ChallengeStartRequest(BaseModel):
    telegram_id: int


class ChallengeStartResponse(BaseModel):
    ok: bool
    attempt_id: int
    match_duration_sec: int
    attempts_today: int
    attempts_left: int
    opponent: dict


class ChallengeFinishRequest(BaseModel):
    telegram_id: int
    attempt_id: int
    my_clicks: int = Field(ge=0)


@router.post("/challenge/start", response_model=ChallengeStartResponse)
async def challenge_start(body: ChallengeStartRequest, session: AsyncSession = Depends(get_async_session)):
    """
    Железный старт:
      - лимит считается по попыткам (START)
      - создаём attempt сразу
      - возвращаем attempt_id + opponent snapshot
    """
    async with session.begin():
        await _cleanup_expired(session)

        me = await _ensure_registered_user(session, body.telegram_id)

        attempts_today = await count_today_challenge_attempts(session, challenger_id=me.id)
        if attempts_today >= CHALLENGE_DAILY_LIMIT:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CHALLENGE_LIMIT",
                    "message": f"Daily limit reached: {attempts_today}/{CHALLENGE_DAILY_LIMIT}",
                    "attempts_today": attempts_today,
                    "limit": CHALLENGE_DAILY_LIMIT,
                },
            )

        my_best = int(getattr(me, "pvp_best_result", 0) or 0)
        low, high = calc_best_result_range(my_best)

        # подбор по диапазону best_result
        q = (
            select(User)
            .where(User.id != me.id)
            .where(func.coalesce(User.pvp_best_result, 0).between(low, high))
            .order_by(func.random())
            .limit(1)
        )
        opp = (await session.execute(q)).scalar_one_or_none()

        # фолбэк: любой случайный
        if not opp:
            opp = (
                await session.execute(
                    select(User).where(User.id != me.id).order_by(func.random()).limit(1)
                )
            ).scalar_one_or_none()

        if not opp:
            raise HTTPException(status_code=404, detail={"code": "NO_OPPONENT", "message": "No opponent found"})

        opp_best = int(getattr(opp, "pvp_best_result", 0) or 0)

        attempt = await create_challenge_attempt(
            session,
            challenger_id=int(me.id),
            opponent_id=int(opp.id),
            opponent_best_result=int(opp_best),
            ttl_minutes=10,
        )

        # пересчитываем после создания, чтобы attempts_left был точным
        attempts_today_after = attempts_today + 1
        return {
            "ok": True,
            "attempt_id": int(attempt.id),
            "match_duration_sec": PVP_MATCH_DURATION_SEC,
            "attempts_today": attempts_today_after,
            "attempts_left": max(0, CHALLENGE_DAILY_LIMIT - attempts_today_after),
            "opponent": {
                "user_id": int(opp.id),
                "telegram_id": int(opp.telegram_id),
                "username": getattr(opp, "username", None),
                "first_name": getattr(opp, "first_name", None),
                "best_result": int(opp_best),
                "victories": int(getattr(opp, "pvp_victories", 0) or 0),
            },
        }


@router.post("/challenge/finish")
async def challenge_finish(body: ChallengeFinishRequest, session: AsyncSession = Depends(get_async_session)):
    """
    Железный finish:
      - attempt должен существовать и принадлежать пользователю
      - attempt должен быть started
      - нельзя завершить дважды
      - если attempt протух по expires_at -> expired и 409
      - пишем историю в challenge_matches и обновляем победы/рекорд
    """
    async with session.begin():
        await _cleanup_expired(session)

        me = await _ensure_registered_user(session, body.telegram_id)

        attempt = await get_challenge_attempt_for_update(session, attempt_id=int(body.attempt_id))
        if not attempt:
            raise HTTPException(status_code=404, detail={"code": "ATTEMPT_NOT_FOUND", "message": "Attempt not found"})

        if int(attempt.challenger_id) != int(me.id):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Attempt does not belong to you"})

        if attempt.status != "started":
            raise HTTPException(status_code=409, detail={"code": "ATTEMPT_NOT_ACTIVE", "message": f"Attempt status is {attempt.status}"})

        now = datetime.now(timezone.utc)
        if attempt.expires_at and now >= attempt.expires_at:
            await expire_challenge_attempt(session, attempt=attempt)
            raise HTTPException(status_code=409, detail={"code": "ATTEMPT_EXPIRED", "message": "Attempt expired"})

        match = await finish_challenge_attempt(
            session,
            attempt=attempt,
            challenger_clicks=int(body.my_clicks),
        )

        return {
            "ok": True,
            "attempt_id": int(attempt.id),
            "match_id": int(match.id),
            "challenger_id": int(match.challenger_id),
            "opponent_id": int(match.opponent_id),
            "challenger_clicks": int(match.challenger_clicks),
            "opponent_best_result": int(match.opponent_best_result),
            "is_win": bool(match.is_win),
            "victories_delta": 1 if bool(match.is_win) else 0,
        }


# --- Legacy (если где-то фронт ещё дергает старое) ---
class ChallengeRunRequest(BaseModel):
    telegram_id: int
    opponent_user_id: int
    my_clicks: int = Field(ge=0)


@router.post("/challenge/run")
async def challenge_run_legacy(body: ChallengeRunRequest, session: AsyncSession = Depends(get_async_session)):
    """
    Legacy: старый режим без start/finish.
    Оставил временно, чтобы ничего не сломать.
    Лучше фронт перевести на /challenge/start + /challenge/finish.
    """
    raise HTTPException(
        status_code=410,
        detail={"code": "DEPRECATED", "message": "Use /challenge/start and /challenge/finish"},
    )


@router.get("/challenge/status")
async def challenge_status(telegram_id: int, session: AsyncSession = Depends(get_async_session)):
    me = await _ensure_registered_user(session, telegram_id)
    attempts_today = await count_today_challenge_attempts(session, challenger_id=me.id)
    return {"ok": True, "attempts_today": attempts_today, "limit": CHALLENGE_DAILY_LIMIT}
