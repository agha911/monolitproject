from __future__ import annotations

from datetime import datetime
from typing import List

from sqlalchemy import BigInteger, String, DateTime, func, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base  # поправь путь, если Base в другом месте


class Partner(Base):
    __tablename__ = "partners"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    tg_username: Mapped[str | None] = mapped_column(String(64))
    tg_user_id: Mapped[int | None] = mapped_column(BigInteger)
    api_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    partner_balance: Mapped[int] = mapped_column(BigInteger, default=0)

    # relations
    drops: Mapped[List["Drop"]] = relationship(
        back_populates="partner",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_partners_name", "name"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Partner id={self.id} slug={self.slug!r}>"
