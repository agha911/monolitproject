# app/crud/boosters.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Tuple, Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.crud.user import get_user_for_update  # уже есть у тебя в проекте


# ——— time helpers ———

def _utcnow() -> datetime:
    """
    Единая точка получения текущего времени в наивном UTC.
    Так избегаем конфликтов aware vs naive при сравнении.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Приводит datetime к наивному UTC (tzinfo=None).
    Если dt уже наивный — возвращает как есть.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _same_utc_date(a: Optional[datetime], b: datetime) -> bool:
    """
    Сравнение только по дате, приводя 'a' к наивному UTC.
    """
    a_naive = _to_naive_utc(a)
    if a_naive is None:
        return False
    return a_naive.date() == b.date()


# ——— internal helpers ———

async def _ensure_daily_window(user: User, now_utc: datetime) -> None:
    """
    Если счётчик бустеров не за сегодня — обнуляем.
    """
    if not _same_utc_date(getattr(user, "booster_success_updated_at", None), now_utc):
        user.booster_success_count = 0
        user.booster_success_updated_at = now_utc


async def _maybe_expire_multiplier(user: User, now_utc: datetime) -> None:
    """
    Сбрасывает временный множитель, если истёк.
    Нормализуем время из БД к наивному UTC перед сравнением.
    """
    exp = _to_naive_utc(getattr(user, "temp_click_multiplier_expires_at", None))
    if exp and now_utc >= exp:
        user.temp_click_multiplier = 1
        user.temp_click_multiplier_expires_at = None


# ——— public API ———

async def can_claim_today(
    session: AsyncSession,
    *,
    user_id: int,
    daily_limit: int = 3
) -> Tuple[bool, int]:
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
    Учитывает дневной лимит успешных бустеров и авто-сброс по дате (UTC).
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
    Все времена сравниваются в наивном UTC.
    """
    now = _utcnow()
    user = await get_user_for_update(session, user_id)
    if not user:
        return {"status": "user_not_found"}

    await _ensure_daily_window(user, now)
    await _maybe_expire_multiplier(user, now)

    current_exp = _to_naive_utc(getattr(user, "temp_click_multiplier_expires_at", None))

    # Если активен — возможен «продлитель»
    new_expires = now + timedelta(seconds=max(1, int(duration_seconds)))
    if current_exp and now < current_exp:
        # Не укорачиваем действующий
        if new_expires < current_exp:
            new_expires = current_exp

    used = int(user.booster_success_count or 0)
    if (not current_exp or now >= current_exp) and used >= daily_limit:
        # Применяем дневной лимит только при НОВОМ старте, а не при продлении активного
        return {"status": "daily_limit_reached", "used": used, "limit": daily_limit}

    # Включаем/продлеваем множитель
    user.temp_click_multiplier = int(multiplier)
    user.temp_click_multiplier_expires_at = new_expires

    # Фиксируем успешный бустер в суточном лимите только при новом старте
    if not current_exp or now >= current_exp:
        user.booster_success_count = used + 1
        user.booster_success_updated_at = now

    await session.flush()
    return {
        "status": "ok",
        "multiplier": user.temp_click_multiplier,
        "expires_at": new_expires.isoformat() + "Z",  # фронту удобно
        "booster_success_count": user.booster_success_count,
        "daily_limit": daily_limit,
        "already_active": bool(current_exp and now < current_exp),
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

