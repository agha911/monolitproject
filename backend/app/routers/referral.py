from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy import select, func, update, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session  # или app.database.get_async_session если у вас так
from app.utils import parse_telegram_user_id
from app.models.user import User
from app.models.referral import ReferralShareEvent, ReferralClaim, ReferralCycle
from app.schemas.referral import ReferralBalanceOut, ReferralClaimOut

# функции времени (Baku)
from app.referral_utils.time_az import baku_now  # у нас теперь роллинг 24ч, day_date не нужен

router = APIRouter()

ROLLING_HOURS = 24


async def _ensure_cycle(session: AsyncSession, referrer_id: int) -> ReferralCycle:
    q = await session.execute(
        select(ReferralCycle).where(ReferralCycle.referrer_id == referrer_id).limit(1)
    )
    row = q.scalar_one_or_none()
    if row:
        return row
    # создаём новый «якорь» окна
    now = baku_now()
    rc = ReferralCycle(referrer_id=referrer_id, anchor_at=now, updated_at=now)
    session.add(rc)
    await session.flush()
    return rc


async def _sum_since_anchor(session: AsyncSession, referrer_id: int, anchor: datetime) -> int:
    # суммируем события, созданные с anchor_at
    sum_q = await session.execute(
        select(func.coalesce(func.sum(ReferralShareEvent.amount), 0)).where(
            ReferralShareEvent.referrer_id == referrer_id,
            ReferralShareEvent.created_at >= anchor,  # Важно: по created_at!
        )
    )
    return int(sum_q.scalar_one() or 0)


@router.get("/referral/balance", response_model=ReferralBalanceOut)
async def get_referral_balance(
    init_data: str = Query(...),
    session: AsyncSession = Depends(get_async_session),
):
    telegram_id = parse_telegram_user_id(init_data)

    res = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user: Optional[User] = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Якори и дедлайны
    cycle = await _ensure_cycle(session, user.id)
    now = baku_now()
    deadline = cycle.anchor_at + timedelta(hours=ROLLING_HOURS)
    seconds_left = max(0, int((deadline - now).total_seconds()))

    # Если просрочено — лениво «сбрасываем» окно
    if now >= deadline:
        # сгорание: окно начинаем заново с текущего момента
        cycle.anchor_at = now
        cycle.updated_at = now
        await session.flush()
        # после «сброса» ничего к выдаче
        return ReferralBalanceOut(
            day_date=now.date().isoformat(),
            amount=0,
            status="expired",
            expires_at_iso=(now + timedelta(hours=ROLLING_HOURS)).isoformat(),
            seconds_left=ROLLING_HOURS * 3600,
        )

    # Не просрочено — считаем сумму с anchor_at
    amount = await _sum_since_anchor(session, user.id, cycle.anchor_at)

    status = "open" if amount > 0 else "none"

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

    res = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user: Optional[User] = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Роллинг-окно 24ч от последнего клейма (anchor_at)
    cycle = await _ensure_cycle(session, user.id)
    now = baku_now()
    deadline = cycle.anchor_at + timedelta(hours=ROLLING_HOURS)

    # Просрочено — сбрасываем якорь, ФИКС: коммитим изменения, чтобы открыть новое окно
    if now >= deadline:
        cycle.anchor_at = now
        cycle.updated_at = now
        session.add(cycle)
        await session.commit()  # <-- критично: иначе окно не открывается
        return ReferralClaimOut(
            status="expired",
            claimed_amount=0,
            total_xp=user.total_xp or 0,
        )

    # Суммируем начисления с момента anchor_at
    amount = await _sum_since_anchor(session, user.id, cycle.anchor_at)
    if amount <= 0:
        return ReferralClaimOut(
            status="nothing",
            claimed_amount=0,
            total_xp=user.total_xp or 0,
        )

    # Выплата пользователю
    user.total_xp = (user.total_xp or 0) + amount
    session.add(user)

    # Аудит клейма (много клеймов допустимо)
    session.add(ReferralClaim(
        referrer_id=user.id,
        day_date=now.date(),
        claimed_amount=amount,
        claimed_at=datetime.utcnow(),  # UTC для аудита
    ))

    # Сбрасываем окно: новый якорь «сейчас»
    cycle.anchor_at = now
    cycle.updated_at = now
    session.add(cycle)

    await session.commit()

    return ReferralClaimOut(
        status="ok",
        claimed_amount=amount,
        total_xp=user.total_xp or 0,
    )


