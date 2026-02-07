# backend/app/api/pvp.py
# Роутер PvP/Challenge в стиле твоего примера challenge.py

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.crud.user import get_user  # получить user по telegram_id
from app.services.pvp_service import (
    finish_live_pvp,
    run_challenge,
    UserNotFound,
    InsufficientCoins,
    ChallengeLimitExceeded,
    InvalidPayload,
)

router = APIRouter(prefix="/api/pvp", tags=["pvp"])


# ====== схемы запросов ======

class LiveFinishRequest(BaseModel):
    telegram_id: int  # инициатор (player1)
    opponent_telegram_id: int  # player2
    player1_clicks: int = Field(ge=0)
    player2_clicks: int = Field(ge=0)
    stake: int = Field(default=50000, ge=0)


class ChallengeRunRequest(BaseModel):
    telegram_id: int  # challenger
    opponent_telegram_id: int
    challenger_clicks: int = Field(ge=0)
    daily_limit: int = Field(default=5, ge=1, le=50)


# ====== endpoints ======

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
