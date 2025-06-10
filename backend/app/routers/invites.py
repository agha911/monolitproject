from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_async_session
from app.models.user import User


router = APIRouter()

@router.get("/api/user/invites")
async def get_user_invites(
    init_data: str,
    session: AsyncSession = Depends(get_async_session),
):
    telegram_id = parse_telegram_user_id(init_data)

    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()

    if not user:
        return {"invited": [False, False, False, False]}

    invited_users = user.invited_users[:4]
    return {"invited": [i < len(invited_users) for i in range(4)]}


