from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from pydantic import BaseModel

from app.database import get_async_session
from app.models.user import User
from app.crud.user import get_user, complete_task, daily_checkin

router = APIRouter()

# 🔧 Модели запроса
class UserIdPayload(BaseModel):
    user_id: int

class TaskPayload(UserIdPayload):
    task_id: str

@router.post("/complete")
async def complete_task_endpoint(payload: TaskPayload, session: AsyncSession = Depends(get_async_session)):
    user = await get_user(session, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    reward = 50  # можно сделать динамически потом
    success = await complete_task(session, user, payload.task_id, reward)

    if not success:
        return {"status": "already_completed"}

    return {
        "status": "success",
        "reward": reward,
        "task_id": payload.task_id
    }

@router.post("/daily_checkin")
async def daily_checkin_endpoint(payload: UserIdPayload, session: AsyncSession = Depends(get_async_session)):
    user = await get_user(session, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    now = datetime.utcnow()
    streak = (user.daily_streak or 0) + 1
    reward = 10 * streak
    updated_user = await daily_checkin(session, user, now, reward, streak)

    return {
        "status": "success",
        "reward": reward,
        "day": updated_user.daily_streak
    }


    now = datetime.utcnow()
    streak = (user.daily_streak or 0) + 1
    reward = 10 * streak
    updated_user = await daily_checkin(session, user, now, reward, streak)
    return {"status": "checked_in", "reward": reward, "streak": updated_user.daily_streak}
