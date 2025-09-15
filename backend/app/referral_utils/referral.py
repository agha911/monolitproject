from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.utils import parse_telegram_user_id
from app.models.user import User
from app.models.referral import ReferralDailyBucket
from app.schemas.referral import ReferralBalanceOut, ReferralClaimOut

# ЕДИНЫЕ утилиты времени и рефералки
from app.utils.time_az import baku_now, baku_today, baku_end_of_today_dt  # :contentReference[oaicite:2]{index=2}
from app.utils.referral import expire_old_buckets  # :contentReference[oaicite:3]{index=3}

router = APIRouter()


@router.get("/api/referral/balance", response_model=ReferralBalanceOut)
async def get_referral_balance(
    init_data: str = Query(..., description="Telegram initData"),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Баланс на сегодня:
    - перед выдачей всегда экспирим «вчерашние» корзины
    - если корзины за сегодня нет и у пользователя есть рефералы -> создаём пустую `open`
    """
    telegram_id = parse_telegram_user_id(init_data)

    # user
    res = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user: Optional[User] = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 1) принудительная экспирация хвостов именно для этого пользователя
    await expire_old_buckets(session, user.id)
    await session.flush()

    # 2) ищем корзину за бакинский "сегодня"
    today = baku_today()
    q = await session.execute(
        select(ReferralDailyBucket).where(
            ReferralDailyBucket.referrer_id == user.id,
            ReferralDailyBucket.day_date == today,
        ).limit(1)
    )
    bucket: Optional[ReferralDailyBucket] = q.scalar_one_or_none()

    # 3) если у пользователя есть рефералы, но корзины за сегодня ещё нет -> создаём пустую `open`
    if bucket is None and (user.invites_count or 0) > 0:
        bucket = ReferralDailyBucket(
            referrer_id=user.id,
            day_date=today,
            amount=0,
            status="open",
        )
        session.add(bucket)
        await session.flush()

    # 4) расчёт таймера до конца бакинского дня
    now_baku = baku_now()
    end_today = baku_end_of_today_dt()
    seconds_left = max(0, int((end_today - now_baku).total_seconds()))

    if not bucket:
        # нет рефералов -> показываем пусто и таймер до конца дня
        return ReferralBalanceOut(
            day_date=str(today),
            amount=0,
            status="none",
            expires_at_iso=end_today.isoformat(),
            seconds_left=seconds_left,
        )

    return ReferralBalanceOut(
        day_date=str(bucket.day_date),
        amount=int(bucket.amount or 0),
        status=bucket.status,  # ожидаем "open"
        expires_at_iso=end_today.isoformat(),
        seconds_left=seconds_left,
    )


@router.post("/api/referral/claim", response_model=ReferralClaimOut)
async def claim_referral_reward(
    payload: dict = Body(...),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Клейм награды:
    - экспирим прошлые дни
    - забираем только сегодняшнюю `open` корзину
    - переводим её в `claimed` и кидаем сумму пользователю в total_xp
    """
    init_data = payload.get("init_data")
    if not init_data:
        raise HTTPException(status_code=400, detail="init_data is required")

    telegram_id = parse_telegram_user_id(init_data)

    # user
    res = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user: Optional[User] = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # экспирим хвосты
    await expire_old_buckets(session, user.id)
    await session.flush()

    # сегодняшняя корзина
    today = baku_today()
    q = await session.execute(
        select(ReferralDailyBucket).where(
            ReferralDailyBucket.referrer_id == user.id,
            ReferralDailyBucket.day_date == today,
        ).limit(1)
    )
    bucket: Optional[ReferralDailyBucket] = q.scalar_one_or_none()

    if not bucket:
        # нет корзины на сегодня
        return ReferralClaimOut(status="nothing", claimed_amount=0)

    if bucket.status == "claimed":
        return ReferralClaimOut(status="already_claimed", claimed_amount=0)

    if bucket.status == "expired":
        return ReferralClaimOut(status="expired", claimed_amount=0)

    amount = int(bucket.amount or 0)
    if amount <= 0:
        return ReferralClaimOut(status="nothing", claimed_amount=0)

    # зачисление пользователю и смена статуса корзины
    user.total_xp = (user.total_xp or 0) + amount
    bucket.status = "claimed"
    bucket.claimed_at = datetime.utcnow()

    session.add_all([user, bucket])
    await session.commit()

    return ReferralClaimOut(status="ok", claimed_amount=amount)

