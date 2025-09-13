# utils/referral.py
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.models.user import User
from app.models.referral import ReferralShareEvent, ReferralDailyBucket

BAKU_TZ = ZoneInfo("Asia/Baku")

def baku_today_date() -> datetime.date:
    return datetime.now(BAKU_TZ).date()

async def expire_old_buckets(session: AsyncSession, referrer_id: int) -> None:
    """Все открытые корзины ранее сегодняшнего дня -> expired."""
    today = baku_today_date()
    await session.execute(
        update(ReferralDailyBucket)
        .where(
            ReferralDailyBucket.referrer_id == referrer_id,
            ReferralDailyBucket.day_date < today,
            ReferralDailyBucket.status == "open",
        )
        .values(status="expired", updated_at=datetime.utcnow())
    )

async def credit_referral_share(session: AsyncSession, source_user_id: int, delta_clicks: int) -> int:
    """
    Начислить 10% рефереру за клики source_user_id.
    Возвращает начисленную сумму (для логов).
    """
    if delta_clicks <= 0:
        return 0

    # Находим реферера (прямой уровень)
    res = await session.execute(select(User).where(User.id == source_user_id))
    src: User | None = res.scalar_one_or_none()
    if not src or not src.invited_by:
        return 0

    referrer_id = src.invited_by
    share = delta_clicks // 10  # 10%, в целых монетах вниз
    if share <= 0:
        return 0

    # Ленивая экспирация прошлых дней
    await expire_old_buckets(session, referrer_id)

    # Аудит-событие
    await session.merge(ReferralShareEvent(
        referrer_id=referrer_id,
        source_user_id=source_user_id,
        day_date=baku_today_date(),
        amount=share,
    ))

    # Обновляем/вставляем дневную корзину
    today = baku_today_date()

    # Пытаемся получить существующую корзину
    q = await session.execute(
        select(ReferralDailyBucket)
        .where(
            ReferralDailyBucket.referrer_id == referrer_id,
            ReferralDailyBucket.day_date == today
        )
        .limit(1)
    )
    bucket = q.scalar_one_or_none()

    if bucket is None:
        bucket = ReferralDailyBucket(
            referrer_id=referrer_id,
            day_date=today,
            amount=share,
            status="open",
        )
        session.add(bucket)
    else:
        if bucket.status == "open":
            bucket.amount += share
            bucket.updated_at = datetime.utcnow()
            session.add(bucket)
        # если корзина уже claimed/expired (бывает при редких гонках) — откроем новую запись текущего дня
        else:
            new_bucket = ReferralDailyBucket(
                referrer_id=referrer_id,
                day_date=today,
                amount=share,
                status="open",
            )
            session.add(new_bucket)

    return share
