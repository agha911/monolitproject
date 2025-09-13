# models/referral.py
from datetime import datetime
from sqlalchemy import (
    BigInteger, Column, Date, DateTime, ForeignKey, String, UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from .base import Base  # ваш Base

class ReferralShareEvent(Base):
    __tablename__ = "referral_share_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    referrer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    source_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    day_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("amount >= 0", name="rse_amount_nonneg"),
    )

    referrer = relationship("User", foreign_keys=[referrer_id])
    source_user = relationship("User", foreign_keys=[source_user_id])


class ReferralDailyBucket(Base):
    __tablename__ = "referral_daily_buckets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    referrer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    day_date: Mapped[datetime] = mapped_column(Date, nullable=False)

    amount: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")  # open|claimed|expired
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    referrer = relationship("User", foreign_keys=[referrer_id])

    __table_args__ = (
        UniqueConstraint("referrer_id", "day_date", name="uq_rdb_referrer_day"),
        CheckConstraint("amount >= 0", name="rdb_amount_nonneg"),
    )
