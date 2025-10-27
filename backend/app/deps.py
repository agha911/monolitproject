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
    request: Request,
    session: AsyncSession = Depends(get_db),
    x_telegram_user_id: str | None = Header(default=None, alias="X-Telegram-User-Id"),
) -> User:
    """
    Авторизация «как везде»:
      - сначала пробуем заголовок X-Telegram-User-Id
      - если его нет (или CORS мешает) — читаем ?telegram_id= в query
    """
    tg_id = x_telegram_user_id or request.query_params.get("telegram_id")
    if not tg_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing telegram id")

    res = await session.execute(select(User).where(User.telegram_id == int(tg_id)).limit(1))
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


