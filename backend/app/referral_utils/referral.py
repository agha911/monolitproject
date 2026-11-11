# utils/referral.py (упрощённый credit_referral_share)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import User
from app.models.referral import ReferralShareEvent
from app.referral_utils.time_az import baku_now
from app.referral_utils.cycle import get_cycle_for_update

async def credit_referral_share(session: AsyncSession, source_user_id: int, delta_clicks: int) -> int:
    if delta_clicks <= 0:
        return 0

    res = await session.execute(select(User).where(User.id == source_user_id))
    src: User | None = res.scalar_one_or_none()
    if not src or not src.invited_by:
        return 0

    share = delta_clicks // 10
    if share <= 0:
        return 0

    await get_cycle_for_update(session, src.invited_by)
    event_at = baku_now()
    session.add(ReferralShareEvent(
        referrer_id=src.invited_by,
        source_user_id=source_user_id,
        day_date=event_at.date(),
        amount=share,
        created_at=event_at,
    ))
    return share


