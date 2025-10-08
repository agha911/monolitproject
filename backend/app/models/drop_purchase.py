from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger, String, DateTime, ForeignKey, func, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from .drop import Drop
from app.models.user import User  # у тебя уже есть эта модель


class DropPurchase(Base):
    __tablename__ = "drop_purchases"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    drop_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("drops.id", ondelete="RESTRICT"), nullable=False)

    unique_code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    # статусы в MVP — текстовые, без ENUM: 'active' | 'redeemed' | 'revoked'
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # relations
    drop: Mapped[Drop] = relationship(back_populates="purchases", lazy="selectin")
    user: Mapped[User] = relationship(backref="drop_purchases", lazy="selectin")

    __table_args__ = (
        Index("ix_dp_user", "user_id"),
        Index("ix_dp_drop", "drop_id"),
        Index("ix_dp_drop_stat", "drop_id", "status"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<DropPurchase id={self.id} code={self.unique_code} status={self.status}>"
