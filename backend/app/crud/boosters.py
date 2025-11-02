# app/crud/boosters.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Tuple, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.crud.user import get_user_for_update  # уже есть у тебя в проекте


# ——— internal helpers ———

def _utcnow() -> datetime:
    # единая точка — дальше проще тестировать/подменять
    return datetime.now(timezone.utc).replace(tzinfo=None)  # храним naive UTC, как у тебя обычно


def _same_utc_date(a: datetime | None, b: datetime) -> bool:
    if a is None:
        return False
    return a.date() == b.date()


async def _ensure_daily_window(user: User, now_utc: datetime) -> None:
    """
    Если счётчик бустеров не за сегодня — обнуляем.
    """
    if not _same_utc_date(user.booster_success_updated_at, now_utc):
        user.booster_success_count = 0
        user.booster_success_updated_at = now_utc


async def _maybe_expire_multiplier(user: User, now_utc: datetime) -> None:
    """
    Сбрасывает временный множитель, если истёк.
    """
    if user.temp_click_multiplier_expires_at and now_utc >= user.temp_click_multiplier_expires_at:
        user.temp_click_multiplier = 1
        user.temp_click_multiplier_expires_at = None


# ——— public API ———

async def can_claim_today(session: AsyncSession, *, user_id: int, daily_limit: int = 3) -> Tuple[bool, int]:
    """
    Проверяет, можно ли сегодня ещё получить бустер.
    Возвращает (ok, remaining).
    """
    now = _utcnow()
    user = await get_user_for_update(session, user_id)
    if not user:
        return False, 0

    await _ensure_daily_window(user, now)
    remaining = max(0, daily_limit - int(user.booster_success_count or 0))
    return (remaining > 0), remaining


async def claim_coin_booster(
    session: AsyncSession,
    *,
    user_id: int,
    amount: int = 50_000,
    daily_limit: int = 3,
) -> Dict[str, Any]:
    """
    Выдаёт одноразовый бустер «+amount GAP».
    Учитывает дневной лимит успешных бустеров и авто-сброс по дате.
    """
    now = _utcnow()
    user = await get_user_for_update(session, user_id)
    if not user:
        return {"status": "user_not_found"}

    # авто-сброс дневного окна и просроченного множителя
    await _ensure_daily_window(user, now)
    await _maybe_expire_multiplier(user, now)

    used = int(user.booster_success_count or 0)
    if used >= daily_limit:
        return {"status": "daily_limit_reached", "used": used, "limit": daily_limit}

    # начисляем монеты и фиксируем успешный бустер
    user.total_xp = int(user.total_xp or 0) + int(amount)
    user.booster_success_count = used + 1
    user.booster_success_updated_at = now

    await session.flush()
    return {
        "status": "ok",
        "granted": amount,
        "booster_success_count": user.booster_success_count,
        "daily_limit": daily_limit,
        "total_xp": user.total_xp,
    }


async def claim_multiplier_booster(
    session: AsyncSession,
    *,
    user_id: int,
    multiplier: int = 10,
    duration_seconds: int = 15,
    daily_limit: int = 3,
) -> Dict[str, Any]:
    """
    Активирует временный множитель клика.
    Если множитель уже активен, продлевает его до max(now + duration, текущее expires).
    """
    now = _utcnow()
    user = await get_user_for_update(session, user_id)
    if not user:
        return {"status": "user_not_found"}

    await _ensure_daily_window(user, now)
    await _maybe_expire_multiplier(user, now)

    used = int(user.booster_success_count or 0)
    if used >= daily_limit:
        return {"status": "daily_limit_reached", "used": used, "limit": daily_limit}

    # включаем/продлеваем множитель
    new_expires = now + timedelta(seconds=max(1, int(duration_seconds)))
    if user.temp_click_multiplier_expires_at:
        # не укорачиваем, если текущий ещё дольше
        if new_expires < user.temp_click_multiplier_expires_at:
            new_expires = user.temp_click_multiplier_expires_at

    user.temp_click_multiplier = int(multiplier)
    user.temp_click_multiplier_expires_at = new_expires

    # фиксируем успешный бустер в суточном лимите
    user.booster_success_count = used + 1
    user.booster_success_updated_at = now

    await session.flush()
    return {
        "status": "ok",
        "multiplier": user.temp_click_multiplier,
        "expires_at": new_expires.isoformat(),
        "booster_success_count": user.booster_success_count,
        "daily_limit": daily_limit,
    }


async def read_effective_multiplier(session: AsyncSession, *, user_id: int) -> int:
    """
    Возвращает фактический множитель (учитывая авто-сброс по истечению).
    Полезно при обработке кликов.
    """
    now = _utcnow()
    user = await get_user_for_update(session, user_id)
    if not user:
        return 1

    await _maybe_expire_multiplier(user, now)
    await session.flush()
    return int(user.temp_click_multiplier or 1)
