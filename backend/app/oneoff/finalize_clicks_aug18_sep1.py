import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.crud_tournament_winner import finalize_tournament_winners
from app.models.db_tournament_winner import TournamentWinner
from app.database import get_async_session  # используем твой существующий провайдер сессии

log = logging.getLogger("oneoff.finalize_clicks")

# --- Конфигурация периода и времени автоснимка ---
AZ  = ZoneInfo("Asia/Baku")
UTC = ZoneInfo("UTC")

# Снимок делаем ровно в 01.09.2025 23:59 по Баку
TARGET_AZ       = datetime(2025, 9, 1, 23, 59, tzinfo=AZ)

# Период турнира «клики»: 18.08.2025 00:00 → 01.09.2025 23:59 (Asia/Baku)
PERIOD_START_AZ = datetime(2025, 8, 18, 0, 0, tzinfo=AZ)
PERIOD_END_AZ   = datetime(2025, 9, 1, 23, 59, tzinfo=AZ)

def _to_naive_utc(dt_az: datetime) -> datetime:
    """Asia/Baku → UTC и убираем tzinfo (TIMESTAMP без TZ в БД)."""
    return dt_az.astimezone(UTC).replace(tzinfo=None)

PERIOD_START = _to_naive_utc(PERIOD_START_AZ)  # 2025-08-17 20:00:00
PERIOD_END   = _to_naive_utc(PERIOD_END_AZ)    # 2025-09-01 19:59:00

# Advisory lock-ключ: дата конца периода YYYYMMDD (для защиты от дублей)
LOCK_KEY = 20250901

@asynccontextmanager
async def session_scope():
    # Берём AsyncSession через твой get_async_session()
    async for s in get_async_session():
        try:
            yield s
        finally:
            await s.close()
        break

async def _already_finalized(session: AsyncSession) -> bool:
    q = await session.execute(
        select(func.count(TournamentWinner.id)).where(
            TournamentWinner.period_start == PERIOD_START,
            TournamentWinner.period_end   == PERIOD_END,
            TournamentWinner.rank_in_league <= 3,
        )
    )
    return (q.scalar() or 0) > 0

async def _finalize_once(session: AsyncSession):
    """Пытаемся единожды зафиксировать победителей за заданный период."""
    # Если уже финализировано — выходим
    if await _already_finalized(session):
        log.info("One-off: already finalized for %s .. %s", PERIOD_START, PERIOD_END)
        return

    # Advisory lock против параллельных инстансов
    locked = (await session.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_KEY})).scalar()
    if not locked:
        log.warning("One-off: advisory lock busy, skip.")
        return

    try:
        # Повторная проверка после захвата лока (на случай гонки)
        if await _already_finalized(session):
            log.info("One-off: already finalized (post-lock).")
            return

        log.info(
            "One-off: finalizing winners. period=%s..%s (UTC naive), target=%s (AZ)",
            PERIOD_START, PERIOD_END, TARGET_AZ
        )
        await finalize_tournament_winners(session, PERIOD_START, PERIOD_END)
        log.info("One-off: finalize OK.")
    finally:
        await session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})

async def run_oneoff_finalize_clicks():
    """
    Одноразовый воркер:
    - если текущее время < TARGET_AZ — ждёт до 01.09.2025 23:59 (Asia/Baku), затем фиксирует;
    - если текущее время >= TARGET_AZ — сразу фиксирует (если ещё не зафиксировано).
    """
    try:
        while True:
            now_az = datetime.now(tz=AZ)
            if now_az >= TARGET_AZ:
                async with session_scope() as session:
                    await _finalize_once(session)
                break  # больше не повторяемся
            # Спим «шагая» максимум по 5 минут (для мягкости при рестартах)
            await asyncio.sleep(min((TARGET_AZ - now_az).total_seconds(), 300))
    except Exception as e:
        log.exception("One-off finalize error: %s", e)

def register_oneoff_finalize_task():
    """
    Регистрирует фоновую таску в текущем event loop.
    Вызывается из main на событии startup одной строкой.
    """
    asyncio.create_task(run_oneoff_finalize_clicks())
