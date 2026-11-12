"""Serialize referral accrual and claims on the same persisted cycle row."""
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.models.referral import ReferralCycle, ReferralShareEvent
from app.referral_utils.time_az import baku_now


async def get_cycle_for_update(session, referrer_id):
    now = baku_now()
    # Preserve recent credits written before cycle initialization existed.
    first = (await session.execute(select(func.min(ReferralShareEvent.created_at)).where(
        ReferralShareEvent.referrer_id == referrer_id,
        ReferralShareEvent.created_at >= now - timedelta(hours=24),
    ))).scalar_one()
    await session.execute(insert(ReferralCycle).values(
        referrer_id=referrer_id, anchor_at=first or now, updated_at=now,
    ).on_conflict_do_nothing(index_elements=[ReferralCycle.referrer_id]))
    return (await session.execute(select(ReferralCycle).where(
        ReferralCycle.referrer_id == referrer_id,
    ).with_for_update().execution_options(populate_existing=True))).scalar_one()
