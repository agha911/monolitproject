# models/referral.py
from datetime import datetime, date
from sqlalchemy import (
    BigInteger, Column, Date, DateTime, ForeignKey, String, UniqueConstraint, CheckConstraint, func, Index
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.database import Base

class ReferralShareEvent(Base):
    __tablename__ = "referral_share_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    referrer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    day_date: Mapped[date] = mapped_column(Date, nullable=False)  # тип аннотации как date
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("amount >= 0", name="rse_amount_nonneg"),
    )

class ReferralClaim(Base):
    __tablename__ = "referral_claims"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    referrer_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    claimed_amount: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # timestamptz на стороне PG: current_timestamp/now() ок для timezone=True
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("claimed_amount >= 0", name="rc_claimed_amount_nonneg"),
        # обычный индекс на (referrer_id, day_date) вместо уникального
        Index("idx_referral_claims_referrer_day", "referrer_id", "day_date"),
    )

class ReferralCycle(Base):
    __tablename__ = "referral_cycle"

    referrer_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True
    )
    anchor_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
