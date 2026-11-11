from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.utils import parse_telegram_user_id
from app.models.user import User
from app.models.referral import ReferralShareEvent, ReferralClaim
from app.schemas.referral import ReferralBalanceOut, ReferralClaimOut

from app.referral_utils.time_az import baku_now
from app.referral_utils.cycle import get_cycle_for_update

router = APIRouter()
ROLLING_HOURS = 24


async def _sum_since_anchor(session: AsyncSession, referrer_id: int, anchor: datetime) -> int:
    # Важно: сумма по created_at, а не по day_date
    sum_q = await session.execute(
        select(func.coalesce(func.sum(ReferralShareEvent.amount), 0)).where(
            ReferralShareEvent.referrer_id == referrer_id,
            ReferralShareEvent.created_at >= anchor,
        )
    )
    return int(sum_q.scalar_one() or 0)


@router.get("/referral/balance", response_model=ReferralBalanceOut)
async def get_referral_balance(
    init_data: str = Query(...),
    session: AsyncSession = Depends(get_async_session),
):
    telegram_id = parse_telegram_user_id(init_data)

    res = await session.execute(select(User).where(User.telegram_id == telegram_id).with_for_update(key_share=True))
    user: Optional[User] = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    cycle = await get_cycle_for_update(session, user.id)
    now = baku_now()
    deadline = cycle.anchor_at + timedelta(hours=ROLLING_HOURS)
    seconds_left = max(0, int((deadline - now).total_seconds()))

    # Если окно просрочено — открываем новое (ленивый reset) и коммитим
    if now >= deadline:
        cycle.anchor_at = now
        cycle.updated_at = now
        session.add(cycle)
        await session.commit()  # критично: сохраняем новый anchor_at

        # пересчитываем новый дедлайн/секунды
        new_deadline = cycle.anchor_at + timedelta(hours=ROLLING_HOURS)
        new_seconds_left = int((new_deadline - now).total_seconds())

        return ReferralBalanceOut(
            day_date=now.date().isoformat(),
            amount=0,
            status="none",  # новое окно, пока ничего не накопилось
            expires_at_iso=new_deadline.isoformat(),
            seconds_left=new_seconds_left,
        )

    # Окно активно — считаем с anchor_at
    amount = await _sum_since_anchor(session, user.id, cycle.anchor_at)
    status = "open" if amount > 0 else "none"
    await session.commit()

    return ReferralBalanceOut(
        day_date=now.date().isoformat(),
        amount=amount,
        status=status,
        expires_at_iso=deadline.isoformat(),
        seconds_left=seconds_left,
    )


@router.post("/referral/claim", response_model=ReferralClaimOut)
async def claim_referral_reward(
    payload: dict = Body(...),
    session: AsyncSession = Depends(get_async_session),
):
    init_data = payload.get("init_data")
    if not init_data:
        raise HTTPException(status_code=400, detail="init_data is required")

    telegram_id = parse_telegram_user_id(init_data)

    res = await session.execute(select(User).where(User.telegram_id == telegram_id).with_for_update(key_share=True))
    user: Optional[User] = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    cycle = await get_cycle_for_update(session, user.id)
    now = baku_now()
    deadline = cycle.anchor_at + timedelta(hours=ROLLING_HOURS)

    # Просрочено — сбрасываем якорь и сохраняем новое окно
    if now >= deadline:
        cycle.anchor_at = now
        cycle.updated_at = now
        session.add(cycle)
        await session.commit()  # фикс «залипания»
        return ReferralClaimOut(
            status="expired",
            claimed_amount=0,
            total_xp=user.total_xp or 0,
        )

    # Сумма с момента anchor_at
    amount = await _sum_since_anchor(session, user.id, cycle.anchor_at)
    if amount <= 0:
        await session.commit()
        return ReferralClaimOut(
            status="nothing_to_claim",
            claimed_amount=0,
            total_xp=user.total_xp or 0,
        )

    # Выплата пользователю
    user.total_xp = (user.total_xp or 0) + amount
    session.add(user)

    # Аудит (множественные клеймы допускаются)
    session.add(ReferralClaim(
        referrer_id=user.id,
        day_date=now.date(),
        claimed_amount=amount,
        claimed_at=datetime.utcnow(),  # UTC лог
    ))

    # Новое окно от текущего момента
    cycle.anchor_at = now
    cycle.updated_at = now
    session.add(cycle)

    await session.commit()

    return ReferralClaimOut(
        status="ok",
        claimed_amount=amount,
        total_xp=user.total_xp or 0,
    )



