from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from pydantic import BaseModel

from app.database import get_async_session
from app.models.user import User
from app.crud.user import get_user, complete_task, daily_checkin, assign_or_get_daily_task, mark_joined_group

router = APIRouter(prefix="/api/task")

# 🔧 Модели запроса
class UserIdPayload(BaseModel):
    user_id: int

class TaskPayload(UserIdPayload):
    task_id: str

class GroupJoinPayload(BaseModel):
    user_id: int

@router.post("/complete")
async def complete_task_endpoint(payload: TaskPayload, session: AsyncSession = Depends(get_async_session)):
    user = await get_user(session, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    reward = 150000  # можно сделать динамически потом
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
        reward = 10000 * streak
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

    reward = 10000 * streak

    # Сохраняем
    updated_user = await daily_checkin(session, user, now, reward, streak)

    return {
        "status": "success",
        "reward": reward,
        "day": updated_user.daily_streak
    }


@router.post("/join_group")
async def join_group_endpoint(payload: GroupJoinPayload, session: AsyncSession = Depends(get_async_session)):
    user = await get_user(session, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    reward = 150000  # Можно менять при необходимости
    success = await mark_joined_group(session, user, reward)

    if not success:
        return {"status": "already_joined"}

    return {
        "status": "success",
        "reward": reward
    }

@router.post("/daily")
async def get_daily_task(payload: UserIdPayload, session: AsyncSession = Depends(get_async_session)):
    user = await get_user(session, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    task = await assign_or_get_daily_task(session, user)

    return {
        "status": "ok",
        **task  # вернёт daily_target, daily_progress, daily_completed
    }
