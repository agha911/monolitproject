from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List

from sqlalchemy import (
    BigInteger, String, Text, Numeric, Boolean, DateTime, ForeignKey, func, Index, CheckConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from .partner import Partner


class Drop(Base):
    __tablename__ = "drops"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    partner_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("partners.id", ondelete="CASCADE"),  # как в упрощённой схеме
        nullable=False,
    )

    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    price_coins: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    per_user_limit: Mapped[int] = mapped_column(nullable=False, server_default="1")
    total_supply: Mapped[int | None] = mapped_column()  # NULL = безлимит

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    visible: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # relations
    partner: Mapped[Partner] = relationship(back_populates="drops", lazy="selectin")
    purchases: Mapped[List["DropPurchase"]] = relationship(
        back_populates="drop", cascade="all, delete-orphan", passive_deletes=True, lazy="selectin"
    )

    __table_args__ = (
        Index("ix_drops_partner", "partner_id"),
        Index("ix_drops_is_active", "active", "visible", "start_at", "end_at"),
        CheckConstraint("discount_percent > 0 AND discount_percent <= 100", name="ck_drops_discount_range"),
        CheckConstraint("end_at > start_at", name="ck_drops_dates"),
        CheckConstraint("price_coins >= 0", name="ck_drops_price_nonneg"),
        CheckConstraint("per_user_limit >= 0", name="ck_drops_per_user_limit_nonneg"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Drop id={self.id} title={self.title!r} active={self.active}>"
