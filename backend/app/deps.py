# app/deps.py
from __future__ import annotations
from typing import AsyncGenerator, Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.models.user import User
from app.models.partner import Partner


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_async_session() as session:
        yield session


async def get_current_user(
    session: AsyncSession = Depends(get_db),
    x_telegram_user_id: int = Header(..., alias="X-Telegram-User-Id"),
) -> User:
    """
    Простой и привычный путь:
    - фронт передает заголовок X-Telegram-User-Id (tg user id)
    - ищем пользователя по users.telegram_id
    - если не найден — считаем, что не зарегистрирован
    """
    res = await session.execute(
        select(User).where(User.telegram_id == int(x_telegram_user_id)).limit(1)
    )
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not registered")
    return user


# Партнёр по API-ключу (оставляем как есть)
async def get_partner_by_api_key(
    x_partner_key: str = Header(..., alias="X-Partner-Key"),
    session: AsyncSession = Depends(get_db),
) -> Partner:
    res = await session.execute(select(Partner).where(Partner.api_key == x_partner_key))
    partner = res.scalar_one_or_none()
    if not partner:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid partner key")
    return partner


