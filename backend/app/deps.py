from __future__ import annotations
from typing import AsyncGenerator, Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session           # твоя фабрика сессий
from app.models.user import User                     # твоя модель пользователя
from app.models.partner import Partner               # из моделей, что мы добавили


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_async_session() as session:
        yield session


# ⚠️ ВСТАВЬ свою реализацию (Telegram initData / JWT и т.п.)
async def get_current_user(session: AsyncSession = Depends(get_db)) -> User:
    # Пример: raise, чтобы не забыть заменить
    raise HTTPException(status_code=501, detail="get_current_user not implemented")


# Партнёр по API-ключу в заголовке X-Partner-Key
async def get_partner_by_api_key(
    x_partner_key: str = Header(..., alias="X-Partner-Key"),
    session: AsyncSession = Depends(get_db),
) -> Partner:
    res = await session.execute(select(Partner).where(Partner.api_key == x_partner_key))
    partner = res.scalar_one_or_none()
    if not partner:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid partner key")
    return partner
