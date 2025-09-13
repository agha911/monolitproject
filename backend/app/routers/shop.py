from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime

from app.database import get_async_session
from app.models.user import User
from app.crud.user import get_user
from app.crud import user as crud_user

router = APIRouter(prefix="/api/shop")

# Константы бустера макс. энергии
MAX_ENERGY_CAP = 30000

# Апгрейд максимальной энергии
ENERGY_INCREMENT = 1000
ENERGY_UPGRADE_COST = 2500      # GAP
DAILY_UPGRADE_LIMIT = 2

# Рефилл энергии
REFILL_COST_GAP = 2500
DAILY_REFILL_LIMIT = 2
        # лимит покупок в сутки

# 🔧 Модель запроса
class UserIdPayload(BaseModel):
    telegram_id: int


@router.post("/buy_max_energy")
async def buy_max_energy_endpoint(payload: UserIdPayload, session: AsyncSession = Depends(get_async_session)):
    # 1) Блокировка строки пользователя (анти‑гонки)
    result = await session.execute(
        select(User).where(User.telegram_id == payload.telegram_id).with_for_update()
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    now = datetime.utcnow()

    # 2) Суточный счётчик
    if user.last_energy_upgrade and user.last_energy_upgrade.date() != now.date():
        user.energy_upgrade_count = 0

    if (user.energy_upgrade_count or 0) >= DAILY_UPGRADE_LIMIT:
        raise HTTPException(status_code=400, detail="Upgrade limit reached for today")

    # 3) Валидации
    if (user.max_energy or 0) >= MAX_ENERGY_CAP:
        raise HTTPException(status_code=400, detail="Max energy cap reached")
    if (user.total_xp or 0) < ENERGY_UPGRADE_COST:
        raise HTTPException(status_code=400, detail="Not enough GAP")

    # 4) Применяем покупку
    user.total_xp = (user.total_xp or 0) - ENERGY_UPGRADE_COST
    user.max_energy = min(MAX_ENERGY_CAP, (user.max_energy or 0) + ENERGY_INCREMENT)

    user.energy_upgrade_count = (user.energy_upgrade_count or 0) + 1
    user.last_energy_upgrade = now

    # 💰 Учитываем траты (если AppStats хранит GAP — передаём стоимость в GAP)
    await crud_user.increment_total_spent(session, ENERGY_UPGRADE_COST)

    await session.commit()

    return {
        "status": "success",
        "new_max_energy": user.max_energy,
        "upgrades_today": user.energy_upgrade_count,
        "limit": DAILY_UPGRADE_LIMIT,
        "total_xp": user.total_xp,
    }


@router.post("/buy_energy_refill")
async def buy_energy_refill_endpoint(payload: UserIdPayload, session: AsyncSession = Depends(get_async_session)):
    # 1) Блокировка строки пользователя (анти‑гонки)
    result = await session.execute(
        select(User).where(User.telegram_id == payload.telegram_id).with_for_update()
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    now = datetime.utcnow()

    # 2) Суточный счётчик
    if user.last_energy_refill and user.last_energy_refill.date() != now.date():
        user.energy_refill_count = 0

    if (user.energy_refill_count or 0) >= DAILY_REFILL_LIMIT:
        raise HTTPException(status_code=400, detail="Refill limit reached for today")

    # 3) Валидации
    if (user.total_xp or 0) < REFILL_COST_GAP:
        raise HTTPException(status_code=400, detail="Not enough GAP")

    # 4) Применяем покупку
    user.total_xp = (user.total_xp or 0) - REFILL_COST_GAP
    user.energy = user.max_energy
    user.energy_refill_count = (user.energy_refill_count or 0) + 1
    user.last_energy_refill = now

    # 💰 Учитываем траты (передаём ту же стоимость, что списали из GAP)
    await crud_user.increment_total_spent(session, REFILL_COST_GAP)

    await session.commit()

    return {
        "status": "success",
        "energy": user.energy,
        "refill_count": user.energy_refill_count
    }

@router.get("/buy_max_energy/status")
async def buy_max_energy_status(telegram_id: int, session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    now = datetime.utcnow()
    upgrades_today = user.energy_upgrade_count or 0
    if user.last_energy_upgrade and user.last_energy_upgrade.date() != now.date():
        upgrades_today = 0  # логический сброс

    return {
        "limit": DAILY_UPGRADE_LIMIT,
        "upgrades_today": upgrades_today,
        "max_energy": user.max_energy,
        "max_energy_cap": MAX_ENERGY_CAP
    }


@router.get("/buy_energy_refill/status")
async def buy_energy_refill_status(telegram_id: int, session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    now = datetime.utcnow()
    refills_today = user.energy_refill_count or 0
    if user.last_energy_refill and user.last_energy_refill.date() != now.date():
        refills_today = 0  # логический сброс

    return {
        "limit": DAILY_REFILL_LIMIT,
        "refills_today": refills_today,
        "current_energy": user.energy,
        "max_energy": user.max_energy
    }


@router.post("/buy_click_boost")
async def buy_click_boost_endpoint(
    payload: UserIdPayload,
    session: AsyncSession = Depends(get_async_session),
):
    INVITE_REQUIREMENTS = {  # требования по наличию приглашённых для ПОКУПАЕМОГО уровня
        6: 1,
        7: 5,
        8: 10,
        9: 15,
        10: 20,
    }
    MAX_LEVEL = 10

    async with session.begin():
        user = await get_user(session, payload.telegram_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # По возможности блокируем строку пользователя (исправь импорт под свой путь)
        try:
            from app.crud.user import get_user_for_update as _get_user_for_update  # noqa
            user = await _get_user_for_update(session, user.id)
        except Exception:
            pass

        if user.click_boost_level is None:
            user.click_boost_level = 0

        current_level = int(user.click_boost_level)
        if current_level >= MAX_LEVEL:
            raise HTTPException(status_code=400, detail="Max boost level reached")

        next_level = current_level + 1

        # Проверяем требования по приглашённым для уровней 6..10
        required_invites = INVITE_REQUIREMENTS.get(next_level, 0)
        if (user.invites_count or 0) < required_invites:
            raise HTTPException(
                status_code=400,
                detail=f"Not enough invited friends for level {next_level} (need {required_invites})",
            )

        # Цена апгрейда — как у тебя было
        price = 5000 * (2 ** current_level)
        if (user.total_xp or 0) < price:
            raise HTTPException(status_code=400, detail="Not enough GAP")

        # Списание и повышение уровня
        user.total_xp = (user.total_xp or 0) - price
        user.click_boost_level = next_level
        session.add(user)

        # 💰 Учитываем траты в GAP-фонде (как и в остальных покупках)
        await crud_user.increment_total_spent(session, price)

    # Коммит произойдёт на выходе из session.begin()
    return {"status": "success", "new_boost_level": user.click_boost_level}










