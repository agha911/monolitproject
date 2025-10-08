from __future__ import annotations
from typing import AsyncGenerator, Optional

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.models.user import User
from app.models.partner import Partner
from app.auth.telegram import verify_init_data, extract_user_id_username, TelegramInitDataError


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_async_session() as session:
        yield session


async def _get_user_by_telegram_id(session: AsyncSession, tg_user_id: int) -> User | None:
    res = await session.execute(
        select(User).where(User.telegram_id == tg_user_id).limit(1)
    )
    return res.scalar_one_or_none()


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_db),
    x_tg_init_data: Optional[str] = Header(default=None, alias="X-Telegram-Init-Data"),
    x_tg_user_id: Optional[int] = Header(default=None, alias="X-Telegram-User-Id"),  # dev fallback
) -> User:
    """
    Приоритет:
      1) X-Telegram-Init-Data (подписанный payload от Telegram WebApp)
      2) X-Telegram-User-Id (для локальных тестов)
    Обязательно проверяем, что пользователь уже зарегистрирован в БД.
    """
    tg_user_id: Optional[int] = None

    if x_tg_init_data:
        try:
            payload = verify_init_data(x_tg_init_data)
            tg_user_id, _ = extract_user_id_username(payload)
        except TelegramInitDataError as e:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"init_data error: {str(e)}")
    elif x_tg_user_id:
        tg_user_id = int(x_tg_user_id)
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Telegram auth data")

    user = await _get_user_by_telegram_id(session, tg_user_id)
    if not user:
        # у тебя регистрация через Bot API — без неё доступ запрещаем
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not registered")
    return user


# партнёр по API-ключу
async def get_partner_by_api_key(
    x_partner_key: str = Header(..., alias="X-Partner-Key"),
    session: AsyncSession = Depends(get_db),
) -> Partner:
    res = await session.execute(select(Partner).where(Partner.api_key == x_partner_key))
    partner = res.scalar_one_or_none()
    if not partner:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid partner key")
    return partner

