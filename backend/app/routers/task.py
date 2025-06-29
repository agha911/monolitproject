from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from pydantic import BaseModel

from app.database import get_async_session
from app.models.user import User
from app.crud.user import get_user, complete_task, daily_checkin

router = APIRouter(prefix="/api/task")

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

    reward = 1000  # можно сделать динамически потом
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
    today = now.date()

    # Если уже отмечался сегодня — ничего не даём
    if user.last_checkin and user.last_checkin.date() == today:
        streak = user.daily_streak or 1
        reward = 100 * streak
        return {
            "status": "already_checked_in",
            "reward": reward,
            "day": streak
        }

    # Проверка: пропущен ли день?
    reset_streak = False
    if user.last_checkin and (today - user.last_checkin.date()).days > 1:
        reset_streak = True

    # Считаем стрик
    streak = 1 if reset_streak else (user.daily_streak or 0) + 1

    # Сброс после 7
    if streak > 7:
        streak = 1

    reward = 100 * streak

    # Сохраняем
    updated_user = await daily_checkin(session, user, now, reward, streak)

    return {
        "status": "success",
        "reward": reward,
        "day": updated_user.daily_streak
    }

