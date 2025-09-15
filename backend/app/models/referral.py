from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import BigInteger, Date, DateTime, func

class ReferralClaim(Base):
    __tablename__ = "referral_claims"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    referrer_id: Mapped[int] = mapped_column(BigInteger, index=True)
    day_date: Mapped[date] = mapped_column(Date, index=True)
    claimed_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
