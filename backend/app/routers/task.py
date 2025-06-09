
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from app.database import get_async_session
from app.models.user import User
from app.crud.user import get_user, complete_task, daily_checkin

router = APIRouter()

@router.post("/complete")
async def complete_task_endpoint(user_id: int, task_id: str, session: AsyncSession = Depends(get_async_session)):
    user = await get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    success = await complete_task(session, user, task_id)
    if not success:
        raise HTTPException(status_code=400, detail="Task already completed")
    return {"status": "completed", "task_id": task_id}

@router.post("/daily_checkin")
async def daily_checkin_endpoint(user_id: int, session: AsyncSession = Depends(get_async_session)):
    user = await get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    now = datetime.utcnow()
    streak = (user.daily_streak or 0) + 1
    reward = 10 * streak
    updated_user = await daily_checkin(session, user, now, reward, streak)
    return {"status": "checked_in", "reward": reward, "streak": updated_user.daily_streak}
