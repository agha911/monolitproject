# app/crud/boosters.py

import logging
from datetime import datetime, timedelta, date
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.crud.user import get_user_for_update

log = logging.getLogger("app.boosters")


# ───────── helpers: время ─────────

def _utcnow() -> datetime:
    """Наивный UTC datetime."""
    return datetime.utcnow()


def _to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Приводим datetime к наивному UTC (если вдруг был с tz)."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(tz=None).replace(tzinfo=None)
    return dt


def _same_utc_date(a: Optional[datetime], b: datetime) -> bool:
    """Проверка: два момента в одну и ту же UTC-дату (по дню)."""
    if a is None:
        return False
    a = _to_naive_utc(a)
    b = _to_naive_utc(b)
    return a.date() == b.date()


# ───────── helpers: дневное окно бустеров ─────────

def _ensure_boosters_daily_window(user: User, now_utc: datetime) -> None:
    """
    Сбрасывает суточные счётчики бустеров, если день сменился.

    Использует поля:
      - daily_booster_claims_coins : int
      - daily_booster_claims_mult  : int
      - boosters_last_reset        : date
    """
    today = now_utc.date()
    last_reset: Optional[date] = getattr(user, "boosters_last_reset", None)

    if last_reset is None or last_reset != today:
        # новый день — обнуляем оба типа бустеров
        user.daily_booster_claims_coins = 0
        user.daily_booster_claims_mult = 0
        user.boosters_last_reset = today
        log.info(
            "boosters.daily_window_reset | user_id=%s telegram_id=%s",
            user.id,
            getattr(user, "telegram_id", None),
        )


def _maybe_expire_multiplier(user: User, now_utc: datetime) -> None:
    """
    Сбрасывает временный множитель, если он истёк.

    Требуемые поля:
      - temp_click_multiplier
      - temp_click_multiplier_expires_at
    """
    exp = _to_naive_utc(getattr(user, "temp_click_multiplier_expires_at", None))
    if exp and now_utc >= exp:
        user.temp_click_multiplier = 1
        user.temp_click_multiplier_expires_at = None
        log.info(
            "boosters.multiplier_expired | user_id=%s telegram_id=%s",
            user.id,
            getattr(user, "telegram_id", None),
        )


# ───────── COIN-бустер (+GAP) ─────────

async def claim_coin_booster(
    session: AsyncSession,
    *,
    user_id: int,
    amount: int = 50_000,
    daily_limit: int = 3,
) -> Dict[str, Any]:
    """
    Выдаёт одноразовый бустер «+amount GAP» (🎁).

    Логика:
      - сбрасываем дневные счётчики, если день сменился;
      - проверяем дневной лимит ИМЕННО для монетных бустеров;
      - если не превышен — начисляем amount в total_xp и +1 в daily_booster_claims_coins.
    """
    now = _utcnow()
    user = await get_user_for_update(session, user_id)
    if not user:
        return {"status": "user_not_found"}

    # синхронизация дневного окна (общая для обоих бустеров)
    _ensure_boosters_daily_window(user, now)
    # на всякий случай проверяем истечение множителя (чтобы состояние было консистентно)
    _maybe_expire_multiplier(user, now)

    used = int(getattr(user, "daily_booster_claims_coins", 0) or 0)
    if used >= daily_limit:
        log.info(
            "boosters.coin.daily_limit_reached | user_id=%s used=%s limit=%s",
            user.id,
            used,
            daily_limit,
        )
        return {
            "status": "daily_limit_reached",
            "used": used,
            "limit": daily_limit,
        }

    before_xp = int(user.total_xp or 0)
    user.total_xp = before_xp + int(amount)
    user.daily_booster_claims_coins = used + 1

    await session.flush()

    log.info(
        "boosters.coin.ok | user_id=%s granted=%s before_xp=%s after_xp=%s used_today=%s limit=%s",
        user.id,
        amount,
        before_xp,
        int(user.total_xp or 0),
        user.daily_booster_claims_coins,
        daily_limit,
    )

    # Чтобы не ломать текущие роуты, дублируем поле used в booster_success_count
    return {
        "status": "ok",
        "type": "coins",
        "granted": amount,
        "used": user.daily_booster_claims_coins,
        "booster_success_count": user.daily_booster_claims_coins,
        "daily_limit": daily_limit,
        "total_xp": int(user.total_xp or 0),
    }


# ───────── MULT-бустер (x10 на время) ─────────

async def claim_multiplier_booster(
    session: AsyncSession,
    *,
    user_id: int,
    multiplier: int = 10,
    duration_seconds: int = 15,
    daily_limit: int = 3,
) -> Dict[str, Any]:
    """
    Выдаёт бустер-множитель клика (🚀), напр. x10 на duration_seconds.

    Логика:
      - сбрасываем дневные счётчики при смене дня;
      - проверяем дневной лимит ИМЕННО для мультипликатора;
      - если не превышен — ставим temp_click_multiplier и expires_at,
        увеличиваем daily_booster_claims_mult.
    """
    now = _utcnow()
    user = await get_user_for_update(session, user_id)
    if not user:
        return {"status": "user_not_found"}

    _ensure_boosters_daily_window(user, now)
    _maybe_expire_multiplier(user, now)

    used = int(getattr(user, "daily_booster_claims_mult", 0) or 0)
    if used >= daily_limit:
        log.info(
            "boosters.mult.daily_limit_reached | user_id=%s used=%s limit=%s",
            user.id,
            used,
            daily_limit,
        )
        return {
            "status": "daily_limit_reached",
            "used": used,
            "limit": daily_limit,
        }

    user.temp_click_multiplier = int(multiplier)
    user.temp_click_multiplier_expires_at = now + timedelta(seconds=duration_seconds)
    user.daily_booster_claims_mult = used + 1

    await session.flush()

    log_info = {
        "user_id": user.id,
        "telegram_id": getattr(user, "telegram_id", None),
        "multiplier": multiplier,
        "duration_seconds": duration_seconds,
        "expires_at": user.temp_click_multiplier_expires_at,
        "used_today": user.daily_booster_claims_mult,
        "limit": daily_limit,
    }
    log.info("boosters.mult.ok | %s", log_info)

    # Также дублируем счётчик в booster_success_count для совместимости с текущими роутами
    return {
        "status": "ok",
        "type": "multiplier",
        "multiplier": multiplier,
        "expires_at": user.temp_click_multiplier_expires_at.isoformat()
        if user.temp_click_multiplier_expires_at
        else None,
        "used": user.daily_booster_claims_mult,
        "booster_success_count": user.daily_booster_claims_mult,
        "daily_limit": daily_limit,
    }



