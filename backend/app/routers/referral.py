from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from deps import get_async_session
from schemas.referral import ReferralBalanceOut, ReferralClaimOut
from utils import parse_telegram_user_id
from utils.time_az import baku_today, baku_end_of_today_dt
from utils.referral import expire_old_buckets
from models.user import User
from models.referral import ReferralDailyBucket

router = APIRouter()

@router.get("/api/referral/balance", response_model=ReferralBalanceOut)
async def get_referral_balance(
    init_data: str = Query(...),
    session: AsyncSession = Depends(get_async_session),
):
    telegram_id = parse_telegram_user_id(init_data)

    async with session.begin():
        user = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = user.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Ленивая экспирация старых корзин
        await expire_old_buckets(session, user.id)

        # Текущая (сегодняшняя) корзина
        today = baku_today()
        q = await session.execute(
            select(ReferralDailyBucket).where(
                ReferralDailyBucket.referrer_id == user.id,
                ReferralDailyBucket.day_date == today
            ).limit(1)
        )
        bucket = q.scalar_one_or_none()

        end_dt = baku_end_of_today_dt()
        now_utc = datetime.now(timezone.utc)
        # seconds_left считаем по Баку-таймзоне, но вернём просто секунды
        seconds_left = int((end_dt - end_dt.tzinfo.fromutc(now_utc)).total_seconds())
        if seconds_left < 0:
            seconds_left = 0

        if bucket is None:
            # ещё не было начислений
            return ReferralBalanceOut(
                day_date=today,
                amount=0,
                status="none",
                expires_at_iso=end_dt.isoformat(),
                seconds_left=seconds_left if seconds_left > 0 else 0,
            )

        # если корзина не open — таймер смысла не имеет
        return ReferralBalanceOut(
            day_date=bucket.day_date,
            amount=bucket.amount,
            status=bucket.status,  # open | claimed | expired
            expires_at_iso=end_dt.isoformat(),
            seconds_left=seconds_left if bucket.status == "open" else 0,
        )


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


