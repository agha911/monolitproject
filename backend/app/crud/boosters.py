import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.crud.user import get_user_for_update

log = logging.getLogger("app.boosters")


# ───── helpers: время / даты ─────

def _utcnow() -> datetime:
    """Возвращает *naive* UTC-datetime, совместимый с БД."""
    return datetime.utcnow().replace(tzinfo=None)


def _to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Приводим datetime к наивному UTC (без tzinfo), если он есть."""
    if not dt:
        return None
    if dt.tzinfo:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _same_utc_date(a: Optional[datetime], b: datetime) -> bool:
    """Проверяем, совпадают ли календарные даты (UTC) двух дат."""
    if not a:
        return False
    au = _to_naive_utc(a)
    bu = _to_naive_utc(b)
    if not au or not bu:
        return False
    return au.date() == bu.date()


# ───── helpers: окно по дням и множитель ─────

def _ensure_boosters_daily_window(user: User, now_utc: datetime) -> None:
    """
    Единая точка для сброса дневных счётчиков бустеров.
    Опирамся на поле user.boosters_last_reset (Date) и сегодняшнюю дату (UTC).

    Требуемые поля в User:
      - daily_booster_claims_coins: int
      - daily_booster_claims_mult: int
      - boosters_last_reset: date
    """
    # если дата последнего ресета бустеров не сегодня — сбрасываем оба счётчика
    last_reset = getattr(user, "boosters_last_reset", None)
    today = _to_naive_utc(now_utc).date() if now_utc else None

    if (not last_reset) or (today and last_reset != today):
        user.daily_booster_claims_coins = 0
        user.daily_booster_claims_mult = 0
        # boosters_last_reset хранится как date, поэтому пишем сегодняшнюю дату
        user.boosters_last_reset = today


def _maybe_expire_multiplier(user: User, now_utc: datetime) -> None:
    """
    Сбрасывает временный множитель, если его время истекло.

    Требуемые поля:
      - temp_click_multiplier: int
      - temp_click_multiplier_expires_at: datetime | None
    """
    exp = _to_naive_utc(getattr(user, "temp_click_multiplier_expires_at", None))
    now_naive = _to_naive_utc(now_utc)
    if exp and now_naive and now_naive >= exp:
        user.temp_click_multiplier = 1
        user.temp_click_multiplier_expires_at = None


def _sync_booster_success_counter(user: User, now_utc: datetime) -> None:
    """
    Для обратной совместимости с роутами, которые читают booster_success_count,
    зеркалим туда сумму дневных использований обоих типов бустеров.
    """
    coins = int(getattr(user, "daily_booster_claims_coins", 0) or 0)
    mults = int(getattr(user, "daily_booster_claims_mult", 0) or 0)
    user.booster_success_count = coins + mults
    user.booster_success_updated_at = _to_naive_utc(now_utc)


# ───── public API: claim_coin_booster ─────

async def claim_coin_booster(
    session: AsyncSession,
    *,
    user_id: int,
    amount: int = 50_000,
    daily_limit: int = 3,
) -> Dict[str, Any]:
    """
    Выдаёт одноразовый бустер «+amount GAP» (🎁).
    Использует СВОЙ дневной лимит (daily_booster_claims_coins).

    При этом:
      - следит за сменой календарного дня и сбрасывает дневные счётчики;
      - аккуратно обновляет booster_success_count для совместимости с фронтом.
    """
    now = _utcnow()
    user = await get_user_for_update(session, user_id)
    if not user:
        return {"status": "user_not_found"}

    # синхронизируем окно и множитель
    _ensure_boosters_daily_window(user, now)
    _maybe_expire_multiplier(user, now)

    used_coins = int(getattr(user, "daily_booster_claims_coins", 0) or 0)
    if used_coins >= daily_limit:
        log.info(
            "boosters.coins.daily_limit_reached | user_id=%s used=%s limit=%s",
            user.id,
            used_coins,
            daily_limit,
        )
        # ВАЖНО: возвращаем used=used_coins, чтобы роуты могли посчитать remaining
        _sync_booster_success_counter(user, now)
        return {
            "status": "daily_limit_reached",
            "used": used_coins,
            "limit": daily_limit,
        }

    # начисляем монеты и увеличиваем только монетный счётчик
    user.total_xp = int(user.total_xp or 0) + int(amount)
    user.daily_booster_claims_coins = used_coins + 1

    # синхронизируем общий booster_success_count
    _sync_booster_success_counter(user, now)

    await session.flush()

    log_info = {
        "user_id": user.id,
        "telegram_id": getattr(user, "telegram_id", None),
        "granted": amount,
        "used_coins_today": user.daily_booster_claims_coins,
        "coins_limit": daily_limit,
        "booster_success_count": user.booster_success_count,
        "total_xp": user.total_xp,
    }
    log.info("boosters.coins.ok | %s", log_info)

    return {
        "status": "ok",
        "type": "coins",
        "granted": amount,
        # для роутов:
        "used": user.daily_booster_claims_coins,
        "booster_success_count": user.booster_success_count,
        "daily_limit": daily_limit,
        "total_xp": user.total_xp,
    }


# ───── public API: claim_multiplier_booster ─────

async def claim_multiplier_booster(
    session: AsyncSession,
    *,
    user_id: int,
    multiplier: int = 10,
    duration_seconds: int = 15,
    daily_limit: int = 3,
) -> Dict[str, Any]:
    """
    Бустер-множитель клика (🚀): ставит temp_click_multiplier = multiplier
    и temp_click_multiplier_expires_at = now + duration_seconds.

    ВАЖНО:
    - дневной лимит считаем по полю daily_booster_claims_mult
      (отдельно от монетного бустера);
    - boosters_last_reset + _ensure_boosters_daily_window() сбрасывают
      daily_booster_claims_coins / daily_booster_claims_mult раз в сутки;
    - для фронта возвращаем поля в СТАРОМ формате:
      type="mult", multiplier, expires_at, booster_success_count.
    """
    now = _utcnow()
    user = await get_user_for_update(session, user_id)
    if not user:
        return {"status": "user_not_found"}

    # сбрасываем дневные счётчики, если наступил новый день
    _ensure_boosters_daily_window(user, now)
    # если старый множитель уже истёк — обнуляем его
    _maybe_expire_multiplier(user, now)

    used_today = int(getattr(user, "daily_booster_claims_mult", 0) or 0)
    if used_today >= daily_limit:
        log.info(
            "boosters.mult.daily_limit_reached | user_id=%s used=%s limit=%s",
            user.id,
            used_today,
            daily_limit,
        )
        return {
            "status": "daily_limit_reached",
            "used": used_today,
            "limit": daily_limit,
        }

    # текущий экспир для флага already_active (как было раньше)
    current_exp = _to_naive_utc(getattr(user, "temp_click_multiplier_expires_at", None))
    new_expires = now + timedelta(seconds=duration_seconds)

    # устанавливаем новый множитель
    user.temp_click_multiplier = int(multiplier)
    user.temp_click_multiplier_expires_at = new_expires

    # обновляем дневной счётчик именно для множителя
    user.daily_booster_claims_mult = used_today + 1

    # поддерживаем старое поле "booster_success_count" как общий агрегат
    user.booster_success_count = int(getattr(user, "booster_success_count", 0) or 0) + 1
    user.booster_success_updated_at = now

    await session.flush()

    log_info = {
        "user_id": user.id,
        "telegram_id": getattr(user, "telegram_id", None),
        "multiplier": multiplier,
        "duration_seconds": duration_seconds,
        "expires_at": new_expires,
        "used_today": user.daily_booster_claims_mult,
        "daily_limit": daily_limit,
    }
    log.info("boosters.mult.ok | %s", log_info)

    # ВАЖНО: форма ответа совместима со старым фронтом
    return {
        "status": "ok",
        "type": "mult",  # как раньше
        "multiplier": multiplier,
        "expires_at": new_expires.isoformat() + "Z",
        # счётчик для фронта (он читает booster_success_count):
        "booster_success_count": user.daily_booster_claims_mult,
        # можно также вернуть и «used», если где-то логика ещё опирается
        "used": user.daily_booster_claims_mult,
        "daily_limit": daily_limit,
        "already_active": bool(current_exp and now < current_exp),
    }





