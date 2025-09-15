# utils/referral.py (упрощённый credit_referral_share)
from sqlalchemy import select
from app.models.user import User
from app.models.referral import ReferralShareEvent
from app.referral_utils.time_az import baku_today  # единый модуль времени

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

    session.add(ReferralShareEvent(
        referrer_id=src.invited_by,
        source_user_id=source_user_id,
        day_date=baku_today(),
        amount=share,
    ))
    return share


