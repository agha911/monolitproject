# app/routers/boosters.py
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.utils import parse_telegram_user_id
from app.crud import user as crud_user
from app.crud.boosters import (
    claim_coin_booster,
    claim_multiplier_booster,
)

router = APIRouter(prefix="/api/boosters", tags=["boosters"])

# Можно вынести в конфиг
COIN_DAILY_LIMIT = 3          # лимит СЕГОДНЯ на бустеры монет
MULT_DAILY_LIMIT = 3          # лимит СЕГОДНЯ на бустеры множителя
COIN_BOOST_AMOUNT = 50_000
MULTIPLIER_VALUE = 10
MULTIPLIER_DURATION_SEC = 15


@router.post("/claim/coins")
async def boosters_claim_coins(
    payload: dict = Body(...),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Активировать бустер «+50 000 GAP».
    Считает собственный дневной лимит (COIN_DAILY_LIMIT).
    """
    init_data = payload.get("init_data")
    if not init_data:
        raise HTTPException(status_code=400, detail="init_data is required")

    telegram_id = parse_telegram_user_id(init_data)
    user = await crud_user.get_user(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="user_not_found")

    res = await claim_coin_booster(
        session=session,
        user_id=user.id,
        amount=COIN_BOOST_AMOUNT,
        daily_limit=COIN_DAILY_LIMIT,
    )
    await session.commit()

    status = res.get("status")
    if status == "ok":
        used_today = int(res.get("booster_success_count", 0))
        remaining = max(0, COIN_DAILY_LIMIT - used_today)
        return {
            "status": "ok",
            "granted": res.get("granted", COIN_BOOST_AMOUNT),
            "total_xp": res.get("total_xp"),
            "used_today": used_today,
            "remaining_today": remaining,
            "daily_limit": COIN_DAILY_LIMIT,
            "type": "coins",
        }
    if status == "daily_limit_reached":
        return {
            "status": "daily_limit_reached",
            "used_today": int(res.get("used", COIN_DAILY_LIMIT)),
            "remaining_today": 0,
            "daily_limit": COIN_DAILY_LIMIT,
            "type": "coins",
        }
    if status == "user_not_found":
        raise HTTPException(status_code=404, detail="user_not_found")
    raise HTTPException(status_code=400, detail=status)


@router.post("/claim/multiplier")
async def boosters_claim_multiplier(
    payload: dict = Body(...),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Активировать временный множитель клика (по умолчанию x10 на 15 секунд).
    Считает собственный дневной лимит (MULT_DAILY_LIMIT).
    Если активен — продлеваем до max(now+duration, текущее expires_at).
    """
    init_data = payload.get("init_data")
    if not init_data:
        raise HTTPException(status_code=400, detail="init_data is required")

    telegram_id = parse_telegram_user_id(init_data)
    user = await crud_user.get_user(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="user_not_found")

    res = await claim_multiplier_booster(
        session=session,
        user_id=user.id,
        multiplier=MULTIPLIER_VALUE,
        duration_seconds=MULTIPLIER_DURATION_SEC,
        daily_limit=MULT_DAILY_LIMIT,
    )
    await session.commit()

    status = res.get("status")
    if status == "ok":
        used_today = int(res.get("booster_success_count", 0))
        remaining = max(0, MULT_DAILY_LIMIT - used_today)
        return {
            "status": "ok",
            "multiplier": res.get("multiplier", MULTIPLIER_VALUE),
            "expires_at": res.get("expires_at"),
            "used_today": used_today,
            "remaining_today": remaining,
            "daily_limit": MULT_DAILY_LIMIT,
            "type": "multiplier",
        }
    if status == "daily_limit_reached":
        return {
            "status": "daily_limit_reached",
            "used_today": int(res.get("used", MULT_DAILY_LIMIT)),
            "remaining_today": 0,
            "daily_limit": MULT_DAILY_LIMIT,
            "type": "multiplier",
        }
    if status == "user_not_found":
        raise HTTPException(status_code=404, detail="user_not_found")
    raise HTTPException(status_code=400, detail=status)

