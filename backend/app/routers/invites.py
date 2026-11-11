from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import get_async_session
from app.models.user import User
from app.utils import parse_telegram_user_id

router = APIRouter()

@router.get("/api/user/invites")
async def get_user_invites(
    init_data: str = Query(...),
    session: AsyncSession = Depends(get_async_session),
):
    telegram_id = parse_telegram_user_id(init_data)

    # 🧠 Не забываем выбрать связь через selectinload
    result = await session.execute(
        select(User)
        .options(selectinload(User.invited_users))
        .where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        return {"count": 0}

    return {"count": len(user.invited_users or [])}





