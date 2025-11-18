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

def _ensure_daily_window_coin(user: User, now_utc: datetime) -> None:
    """
    Сбрасывает суточный счётчик монетных бустеров, если дата сменилась.
    Требуемые поля (уже добавлены в модель User):
      - coin_booster_success_count: int
      - coin_booster_updated_at: datetime | None
    """
    if not _same_utc_date(getattr(user, "coin_booster_updated_at", None), now_utc):
        user.coin_booster_success_count = 0
        user.coin_booster_updated_at = now_utc


def _ensure_daily_window_mult(user: User, now_utc: datetime) -> None:
    """
    Сбрасывает суточный счётчик бустеров-множителей, если дата сменилась.
    Требуемые поля:
      - mult_booster_success_count: int
      - mult_booster_updated_at: datetime | None
    """
    if not _same_utc_date(getattr(user, "mult_booster_updated_at", None), now_utc):
        user.mult_booster_success_count = 0
        user.mult_booster_updated_at = now_utc


def _maybe_expire_multiplier(user: User, now_utc: datetime) -> None:
    """
    Сбрасывает временный множитель, если истёк.
    Требуемые поля:
      - temp_click_multiplier: int
      - temp_click_multiplier_expires_at: datetime | None
    """
    exp = _to_naive_utc(getattr(user, "temp_click_multiplier_expires_at", None))
    if exp and now_utc >= exp:
        user.temp_click_multiplier = 1
        user.temp_click_multiplier_expires_at = None


# ——— public API (раздельные лимиты по типам) ———

async def can_claim_today_coin(
    session: AsyncSession,
    *,
    user_id: int,
    daily_limit: int = 3,
) -> Tuple[bool, int]:
    """
    Проверяет возможность получения монетного бустера за сегодня.
    Возвращает (ok, remaining).
    """
    now = _utcnow()
    user = await get_user_for_update(session, user_id)
    if not user:
        return False, 0

    _ensure_daily_window_coin(user, now)
    remaining = max(0, daily_limit - int(user.coin_booster_success_count or 0))
    return (remaining > 0), remaining


async def can_claim_today_mult(
    session: AsyncSession,
    *,
    user_id: int,
    daily_limit: int = 3,
) -> Tuple[bool, int]:
    """
    Проверяет возможность получения бустера-множителя за сегодня.
    Возвращает (ok, remaining).
    """
    now = _utcnow()
    user = await get_user_for_update(session, user_id)
    if not user:
        return False, 0

    _ensure_daily_window_mult(user, now)
    remaining = max(0, daily_limit - int(user.mult_booster_success_count or 0))
    return (remaining > 0), remaining


async def claim_coin_booster(
    session: AsyncSession,
    *,
    user_id: int,
    amount: int = 50_000,
    daily_limit: int = 3,
) -> Dict[str, Any]:
    """
    Выдаёт одноразовый бустер «+amount GAP» (🎁).
    Учитывает дневной лимит ИМЕННО для монетных бустеров.
    """
    now = _utcnow()
    user = await get_user_for_update(session, user_id)
    if not user:
        return {"status": "user_not_found"}

    # авто-сброс окна и проверка мультипликатора
    _ensure_daily_window_coin(user, now)
    _maybe_expire_multiplier(user, now)

    used = int(user.coin_booster_success_count or 0)
    if used >= daily_limit:
        return {"status": "daily_limit_reached", "used": used, "limit": daily_limit}

    # начисляем монеты и фиксируем успешный монетный бустер
    user.total_xp = int(user.total_xp or 0) + int(amount)
    user.coin_booster_success_count = used + 1
    user.coin_booster_updated_at = now

    await session.flush()
    return {
        "status": "ok",
        "type": "coins",
        "granted": amount,
        "used": user.coin_booster_success_count,
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
    Активирует (или продлевает) бустер-множитель (🚀).
    Лимит — ТОЛЬКО по бустерам-множителям. Продление активного эффекта
    не тратит суточную попытку.
    """
    now = _utcnow()
    user = await get_user_for_update(session, user_id)
    if not user:
        return {"status": "user_not_found"}

    _ensure_daily_window_mult(user, now)
    _maybe_expire_multiplier(user, now)

    current_exp = _to_naive_utc(getattr(user, "temp_click_multiplier_expires_at", None))
    new_expires = now + timedelta(seconds=max(1, int(duration_seconds)))

    # если активен — не укорачиваем
    if current_exp and now < current_exp and new_expires < current_exp:
        new_expires = current_exp

    used = int(user.mult_booster_success_count or 0)
    starting_new = (not current_exp) or (now >= current_exp)

    if starting_new and used >= daily_limit:
        return {"status": "daily_limit_reached", "used": used, "limit": daily_limit}

    # Включаем/продлеваем множитель
    user.temp_click_multiplier = int(multiplier)
    user.temp_click_multiplier_expires_at = new_expires

    # Новая активация — засчитываем попытку
    if starting_new:
        user.mult_booster_success_count = used + 1
        user.mult_booster_updated_at = now

    await session.flush()
    return {
        "status": "ok",
        "type": "mult",
        "multiplier": user.temp_click_multiplier,
        "expires_at": new_expires.isoformat() + "Z",
        "used": user.mult_booster_success_count,
        "daily_limit": daily_limit,
        "already_active": bool(current_exp and now < current_exp),
    }


async def read_effective_multiplier(session: AsyncSession, *, user_id: int) -> int:
    """
    Возвращает фактический множитель (учитывая авто-сброс по истечению).
    """
    now = _utcnow()
    user = await get_user_for_update(session, user_id)
    if not user:
        return 1

    _maybe_expire_multiplier(user, now)
    await session.flush()
    return int(user.temp_click_multiplier or 1)



