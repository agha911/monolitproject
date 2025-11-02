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

# Можно вынести в конфиг при желании
DAILY_LIMIT = 3
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
    Учитывает дневной лимит успешных бустеров.
    """
    init_data = payload.get("init_data")
    if not init_data:
        raise HTTPException(status_code=400, detail="init_data is required")

    telegram_id = parse_telegram_user_id(init_data)
    user = await crud_user.get_user(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="user_not_found")

    res = await claim_coin_booster(
        session,
        user_id=user.id,
        amount=COIN_BOOST_AMOUNT,
        daily_limit=DAILY_LIMIT,
    )

    # фиксируем изменения
    await session.commit()

    # Нормализуем ответ
    status = res.get("status")
    if status == "ok":
        remaining = max(0, DAILY_LIMIT - int(res.get("booster_success_count", 0)))
        return {
            "status": "ok",
            "granted": res.get("granted", COIN_BOOST_AMOUNT),
            "total_xp": res.get("total_xp"),
            "used_today": res.get("booster_success_count"),
            "remaining_today": remaining,
            "daily_limit": DAILY_LIMIT,
        }
    elif status == "daily_limit_reached":
        return {
            "status": "daily_limit_reached",
            "used_today": res.get("used"),
            "remaining_today": 0,
            "daily_limit": DAILY_LIMIT,
        }
    elif status == "user_not_found":
        raise HTTPException(status_code=404, detail="user_not_found")
    else:
        # на всякий случай
        raise HTTPException(status_code=400, detail=status)


@router.post("/claim/multiplier")
async def boosters_claim_multiplier(
    payload: dict = Body(...),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Активировать временный множитель клика (по умолчанию x10 на 15 секунд).
    Если множитель уже активен – продляем до max(now+duration, текущее expires_at).
    """
    init_data = payload.get("init_data")
    if not init_data:
        raise HTTPException(status_code=400, detail="init_data is required")

    telegram_id = parse_telegram_user_id(init_data)
    user = await crud_user.get_user(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="user_not_found")

    res = await claim_multiplier_booster(
        session,
        user_id=user.id,
        multiplier=MULTIPLIER_VALUE,
        duration_seconds=MULTIPLIER_DURATION_SEC,
        daily_limit=DAILY_LIMIT,
    )

    # фиксируем изменения
    await session.commit()

    status = res.get("status")
    if status == "ok":
        remaining = max(0, DAILY_LIMIT - int(res.get("booster_success_count", 0)))
        return {
            "status": "ok",
            "multiplier": res.get("multiplier"),
            "expires_at": res.get("expires_at"),
            "used_today": res.get("booster_success_count"),
            "remaining_today": remaining,
            "daily_limit": DAILY_LIMIT,
        }
    elif status == "daily_limit_reached":
        return {
            "status": "daily_limit_reached",
            "used_today": res.get("used"),
            "remaining_today": 0,
            "daily_limit": DAILY_LIMIT,
        }
    elif status == "user_not_found":
        raise HTTPException(status_code=404, detail="user_not_found")
    else:
        raise HTTPException(status_code=400, detail=status)
