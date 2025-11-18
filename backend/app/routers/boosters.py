from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.crud import user as crud_user
from app.crud.boosters import (
    claim_coin_booster,
    claim_multiplier_booster,
)
from app.utils import parse_telegram_user_id

router = APIRouter(
    prefix="/api/boosters",
    tags=["boosters"],
)

# Константы бустеров — должны совпадать с фронтом
COIN_BOOST_AMOUNT = 50_000      # 🎁 +50k GAP
COIN_DAILY_LIMIT = 3            # до 3 подарочных бустеров в сутки

MULT_FACTOR = 10                # 🚀 множитель x10
MULT_DURATION_SECONDS = 15      # до 15 секунд
MULT_DAILY_LIMIT = 3            # до 3 мульти-бустеров в сутки


# ───────────────── БУСТЕР МОНЕТ (🎁) ─────────────────

@router.post("/claim/coins")
async def boosters_claim_coins(
    payload: dict = Body(...),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Активировать бустер «+50 000 GAP».
    Считает СВОЙ дневной лимит (COIN_DAILY_LIMIT), независимый от бустера множителя.
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
        # ⚠️ важно: используем те ключи, которые реально возвращает crud-функция
        used_today = int(res.get("used", 0))
        remaining = max(0, COIN_DAILY_LIMIT - used_today)
        return {
            "status": "ok",
            "type": "coins",
            "granted": int(res.get("granted", COIN_BOOST_AMOUNT)),
            "total_xp": int(res.get("total_xp", 0)),
            "used_today": used_today,
            "remaining_today": remaining,
            "daily_limit": COIN_DAILY_LIMIT,
        }

    if status == "daily_limit_reached":
        used_today = int(res.get("used", COIN_DAILY_LIMIT))
        return {
            "status": "daily_limit_reached",
            "type": "coins",
            "used_today": used_today,
            "remaining_today": 0,
            "daily_limit": COIN_DAILY_LIMIT,
        }

    if status == "user_not_found":
        raise HTTPException(status_code=404, detail="user_not_found")

    # на всякий случай
    raise HTTPException(status_code=400, detail=str(status))


# ───────────────── БУСТЕР МНОЖИТЕЛЯ (🚀) ─────────────────

@router.post("/claim/multiplier")
async def boosters_claim_multiplier(
    payload: dict = Body(...),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Активировать бустер «x10 на 15 секунд».
    Считает СВОЙ дневной лимит (MULT_DAILY_LIMIT), независимый от монетного бустера.
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
        multiplier=MULT_FACTOR,
        duration_seconds=MULT_DURATION_SECONDS,
        daily_limit=MULT_DAILY_LIMIT,
    )
    await session.commit()

    status = res.get("status")

    if status == "ok":
        # crud-функция должна вернуть expires_at (datetime) в ISO или мы сами конвертим
        expires_at = res.get("expires_at")  # ожидаем ISO-строку
        used_today = int(res.get("used", 0))
        remaining = max(0, MULT_DAILY_LIMIT - used_today)
        return {
            "status": "ok",
            "type": "multiplier",
            "factor": int(res.get("factor", MULT_FACTOR)),
            "expires_at": expires_at,  # фронт берёт это поле
            "used_today": used_today,
            "remaining_today": remaining,
            "daily_limit": MULT_DAILY_LIMIT,
        }

    if status == "daily_limit_reached":
        used_today = int(res.get("used", MULT_DAILY_LIMIT))
        return {
            "status": "daily_limit_reached",
            "type": "multiplier",
            "used_today": used_today,
            "remaining_today": 0,
            "daily_limit": MULT_DAILY_LIMIT,
        }

    if status == "user_not_found":
        raise HTTPException(status_code=404, detail="user_not_found")

    raise HTTPException(status_code=400, detail=str(status))

