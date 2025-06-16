from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_async_session
from app.models.user import User
from app.crud.user import get_user, buy_max_energy
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/shop")

# 🔧 Модель запроса
class UserIdPayload(BaseModel):
    user_id: int

@router.post("/buy_max_energy")
async def buy_max_energy_endpoint(payload: UserIdPayload, session: AsyncSession = Depends(get_async_session)):
    user = await get_user(session, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    success = await buy_max_energy(session, user)
    if not success:
        raise HTTPException(status_code=400, detail="Not enough XP to buy energy")

    return {"status": "success", "new_max_energy": user.max_energy}


# ✅ Новый эндпоинт — восстановление энергии
from datetime import datetime, timedelta

@router.post("/buy_energy_refill")
async def buy_energy_refill_endpoint(payload: UserIdPayload, session: AsyncSession = Depends(get_async_session)):
    user = await get_user(session, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    now = datetime.utcnow()
    refill_limit = 2

    # Сброс счётчика, если день сменился
    if user.last_energy_refill:
        if user.last_energy_refill.date() != now.date():
            user.energy_refill_count = 0

    if user.energy_refill_count >= refill_limit:
        raise HTTPException(status_code=400, detail="Refill limit reached for today")

    # Проверка на достаточное количество монет
    if user.total_xp < 500:
        raise HTTPException(status_code=400, detail="Not enough GAP")

    user.total_xp -= 500
    user.energy = user.max_energy
    user.energy_refill_count += 1
    user.last_energy_refill = now

    session.add(user)
    await session.commit()

    return {
        "status": "success",
        "energy": user.energy,
        "refill_count": user.energy_refill_count
    }

