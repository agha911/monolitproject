from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.schemas.referral import ReferralBalanceOut, ReferralClaimOut
from app.utils import parse_telegram_user_id
from app.referral_utils.time_az import baku_today, baku_end_of_today_dt
from app.referral_utils.referral import expire_old_buckets
from app.models.user import User
from app.models.referral import ReferralDailyBucket

router = APIRouter()

@router.get("/api/referral/balance", response_model=ReferralBalanceOut)
async def referral_balance(
    init_data: str = Query(...),
    session: AsyncSession = Depends(get_async_session),
):
    telegram_id = parse_telegram_user_id(init_data)

    res = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # ✅ Принудительная экспирация старых корзин прямо при запросе баланса
    await expire_old_buckets(session, user.id)
    await session.flush()

    today = baku_today_date()
    q = await session.execute(
        select(ReferralDailyBucket)
        .where(
            ReferralDailyBucket.referrer_id == user.id,
            ReferralDailyBucket.day_date == today
        )
        .limit(1)
    )
    bucket = q.scalar_one_or_none()

    # Расчёт таймера: конец бакинского дня минус текущее бакинское время
    now_baku = datetime.now(BAKU_TZ)
    end_today = baku_end_of_today_dt()
    seconds_left = max(0, int((end_today - now_baku).total_seconds()))

    if not bucket:
        return {
            "day_date": str(today),
            "amount": 0,
            "status": "none",
            "expires_at_iso": end_today.isoformat(),
            "seconds_left": seconds_left,
        }

    return {
        "day_date": str(bucket.day_date),
        "amount": int(bucket.amount or 0),
        "status": bucket.status,  # ожидаем "open" для сегодняшней корзины
        "expires_at_iso": end_today.isoformat(),
        "seconds_left": seconds_left,
    }


@router.post("/api/referral/claim", response_model=ReferralClaimOut)
async def post_referral_claim(
    data: dict = Body(...),
    session: AsyncSession = Depends(get_async_session),
):
    init_data = data.get("init_data")
    if not init_data:
        raise HTTPException(status_code=400, detail="init_data is required")

    telegram_id = parse_telegram_user_id(init_data)

    async with session.begin():
        user = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = user.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # закрываем старые open корзины
        await expire_old_buckets(session, user.id)

        # сегодняшняя корзина
        today = baku_today()
        q = await session.execute(
            select(ReferralDailyBucket).where(
                ReferralDailyBucket.referrer_id == user.id,
                ReferralDailyBucket.day_date == today
            ).limit(1)
        )
        bucket = q.scalar_one_or_none()

        if bucket is None or bucket.amount <= 0:
            return ReferralClaimOut(
                status="nothing_to_claim",
                claimed_amount=0,
                total_xp=user.total_xp or 0,
            )

        if bucket.status == "claimed":
            return ReferralClaimOut(
                status="already_claimed",
                claimed_amount=0,
                total_xp=user.total_xp or 0,
            )
        if bucket.status == "expired":
            return ReferralClaimOut(
                status="expired",
                claimed_amount=0,
                total_xp=user.total_xp or 0,
            )

        # статус open: переводим в total_xp и помечаем claimed
        claim_amount = int(bucket.amount)
        user.total_xp = (user.total_xp or 0) + claim_amount
        bucket.status = "claimed"
        bucket.claimed_at = datetime.now(timezone.utc)

        session.add_all([user, bucket])

        return ReferralClaimOut(
            status="ok",
            claimed_amount=claim_amount,
            total_xp=user.total_xp or 0,
        )


