
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_async_session
from app.models.user import User
from app.crud import get_user, buy_max_energy

router = APIRouter()

@router.post("/buy_max_energy")
async def buy_max_energy_endpoint(user_id: int, session: AsyncSession = Depends(get_async_session)):
    user = await get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    success = await buy_max_energy(session, user)
    if not success:
        raise HTTPException(status_code=400, detail="Not enough XP to buy energy")
    return {"status": "success", "new_max_energy": user.max_energy}
