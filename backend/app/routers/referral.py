# app/routers/referral.py
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.utils import parse_telegram_user_id
from app.models.user import User
from app.models.referral import ReferralShareEvent, ReferralClaim
from app.schemas.referral import ReferralBalanceOut, ReferralClaimOut

# единые функции времени
from app.referral_utils.time_az import baku_now, baku_today, baku_end_of_today_dt  # :contentReference[oaicite:2]{index=2}

router = APIRouter()

@router.get("/api/referral/balance", response_model=ReferralBalanceOut)
async def get_referral_balance(
    init_data: str = Query(...),
    session: AsyncSession = Depends(get_async_session),
):
    telegram_id = parse_telegram_user_id(init_data)

    res = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user: Optional[User] = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    today = baku_today()

    # сумма событий за сегодня
    sum_q = await session.execute(
        select(func.coalesce(func.sum(ReferralShareEvent.amount), 0))
        .where(
            ReferralShareEvent.referrer_id == user.id,
            ReferralShareEvent.day_date == today
        )
    )
    amount_today: int = int(sum_q.scalar_one() or 0)

    # был ли клейм сегодня
    claim_q = await session.execute(
        select(ReferralClaim).where(
            ReferralClaim.referrer_id == user.id,
            ReferralClaim.day_date == today
        ).limit(1)
    )
    claim = claim_q.scalar_one_or_none()

    now_baku = baku_now()
    end_today = baku_end_of_today_dt()
    seconds_left = max(0, int((end_today - now_baku).total_seconds()))

    if claim:
        status = "claimed"
    else:
        if amount_today <= 0:
            status = "none"
        else:
            # если день уже закончился и не клеймлено — считаем "expired"
            status = "expired" if seconds_left == 0 else "open"

    return ReferralBalanceOut(
        day_date=str(today),
        amount=amount_today,
        status=status,                  # open/claimed/expired/none
        expires_at_iso=end_today.isoformat(),
        seconds_left=seconds_left,
    )


@router.post("/api/referral/claim", response_model=ReferralClaimOut)
async def claim_referral_reward(
    payload: dict = Body(...),
    session: AsyncSession = Depends(get_async_session),
):
    init_data = payload.get("init_data")
    if not init_data:
        raise HTTPException(status_code=400, detail="init_data is required")

    telegram_id = parse_telegram_user_id(init_data)

    res = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user: Optional[User] = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    today = baku_today()
    now_baku = baku_now()
    end_today = baku_end_of_today_dt()

    # проверим «уже забрано»
    claim_q = await session.execute(
        select(ReferralClaim).where(
            ReferralClaim.referrer_id == user.id,
            ReferralClaim.day_date == today
        ).limit(1)
    )
    claim = claim_q.scalar_one_or_none()
    if claim:
        return ReferralClaimOut(status="already_claimed", claimed_amount=0)

    # сумма событий за сегодня
    sum_q = await session.execute(
        select(func.coalesce(func.sum(ReferralShareEvent.amount), 0))
        .where(
            ReferralShareEvent.referrer_id == user.id,
            ReferralShareEvent.day_date == today
        )
    )
    amount_today: int = int(sum_q.scalar_one() or 0)

    if amount_today <= 0:
        return ReferralClaimOut(status="nothing", claimed_amount=0)

    # если уже наступил следующий день по Баку — «expired»
    if now_baku >= end_today:
        return ReferralClaimOut(status="expired", claimed_amount=0)

    # клеймим: фиксируем запись и начисляем пользователю
    user.total_xp = (user.total_xp or 0) + amount_today
    new_claim = ReferralClaim(
        referrer_id=user.id,
        day_date=today,
        claimed_amount=amount_today,
        claimed_at=datetime.utcnow(),   # UTC-аудит времени клейма
    )
    session.add_all([user, new_claim])
    await session.commit()

    return ReferralClaimOut(status="ok", claimed_amount=amount_today)


