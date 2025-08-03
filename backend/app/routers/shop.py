from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from datetime import datetime

from app.database import get_async_session
from app.models.user import User
from app.crud.user import get_user, buy_max_energy
from app.crud import stats as crud_stats
from app.crud import user as crud_user

router = APIRouter(prefix="/api/shop")

# 🔧 Модель запроса
class UserIdPayload(BaseModel):
    telegram_id: int

@router.post("/buy_max_energy")
async def buy_max_energy_endpoint(payload: UserIdPayload, session: AsyncSession = Depends(get_async_session)):
    user = await get_user(session, payload.telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    success = await buy_max_energy(session, user)
    if not success:
        raise HTTPException(status_code=400, detail="Not enough XP to buy energy")

    # 💰 Учитываем траты
    await crud_user.increment_spent(session, user.telegram_id, 5000)
    await crud_stats.increment_total_spent(session, 5000)

    return {"status": "success", "new_max_energy": user.max_energy}



# ✅ Восполнение энергии
@router.post("/buy_energy_refill")
async def buy_energy_refill_endpoint(payload: UserIdPayload, session: AsyncSession = Depends(get_async_session)):
    user = await get_user(session, payload.telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    now = datetime.utcnow()
    refill_limit = 2

    if user.last_energy_refill and user.last_energy_refill.date() != now.date():
        user.energy_refill_count = 0

    if user.energy_refill_count >= refill_limit:
        raise HTTPException(status_code=400, detail="Refill limit reached for today")

    if user.total_xp < 500:
        raise HTTPException(status_code=400, detail="Not enough GAP")

    user.total_xp -= 500
    user.energy = user.max_energy
    user.energy_refill_count += 1
    user.last_energy_refill = now

    session.add(user)

    # 💰 Учитываем траты
    await crud_user.increment_spent(session, user.telegram_id, 500)
    await crud_stats.increment_total_spent(session, 500)

    await session.commit()

    return {
        "status": "success",
        "energy": user.energy,
        "refill_count": user.energy_refill_count
    }



# ✅ Новый эндпоинт — покупка бустера на клик
@router.post("/buy_click_boost")
async def buy_click_boost_endpoint(payload: UserIdPayload, session: AsyncSession = Depends(get_async_session)):
    user = await get_user(session, payload.telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.click_boost_level is None:
        user.click_boost_level = 0

    current_level = user.click_boost_level

    if current_level >= 4:
        raise HTTPException(status_code=400, detail="Max boost level reached")

    price = 5000 * (2 ** current_level)
    if user.total_xp < price:
        raise HTTPException(status_code=400, detail="Not enough GAP")

    user.total_xp -= price
    user.click_boost_level = current_level + 1

    session.add(user)

    # 💰 Учитываем траты
    await crud_user.increment_spent(session, user.telegram_id, price)
    await crud_stats.increment_total_spent(session, price)

    await session.commit()

    return {"status": "success", "new_boost_level": user.click_boost_level}





