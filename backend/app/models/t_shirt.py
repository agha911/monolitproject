from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column

# ВАЖНО: Base импортируй оттуда, где он у тебя уже объявлен
from app.database import Base
from app.models.user import User


class TshirtSize(str, enum.Enum):
    S = "S"
    M = "M"
    L = "L"


class PassiveIncomeSource(str, enum.Enum):
    TSHIRT = "tshirt"


class TshirtDrop(Base):
    __tablename__ = "tshirt_drop"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False, default="Gappick T-shirt")

    total_stock: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    sold_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    sale_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sold_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    purchases = relationship("TshirtPurchase", back_populates="drop", lazy="selectin")

    __table_args__ = (
        Index("ix_tshirt_drop_active", "is_active"),
    )


class TshirtPurchase(Base):
    __tablename__ = "tshirt_purchases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    drop_id: Mapped[int] = mapped_column(ForeignKey("tshirt_drop.id", ondelete="RESTRICT"), nullable=False)

    size: Mapped[TshirtSize] = mapped_column(Enum(TshirtSize), nullable=False)

    # Цена в $GAP (сколько списали у пользователя)
    price_gap: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Сколько зачислили в фонд (обычно = price_gap, но поле оставляем для гибкости)
    fund_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Если потом появится "ledger/tx id" фонда — сюда можно положить связку
    fund_tx_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    purchased_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # На будущее: статус покупки (пока можно всегда считать confirmed)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="confirmed")

    user = relationship("User", lazy="selectin")
    drop = relationship("TshirtDrop", back_populates="purchases", lazy="selectin")

    __table_args__ = (
        # Если 1 футболка на пользователя — оставляем так (рекомендую)
        UniqueConstraint("user_id", "drop_id", name="uq_tshirt_purchase_user_drop"),
        Index("ix_tshirt_purchases_user_id", "user_id"),
        Index("ix_tshirt_purchases_drop_id", "drop_id"),
    )


class PassiveIncomeCard(Base):
    __tablename__ = "passive_income_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # ✅ FIX: используем value ("tshirt"), а не имя Enum-члена ("TSHIRT"),
    # и привязываемся к существующему PG enum-типу passiveincomesource.
    source: Mapped[PassiveIncomeSource] = mapped_column(
        Enum(
            PassiveIncomeSource,
            name="passiveincomesource",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
            native_enum=True,
        ),
        nullable=False,
        default=PassiveIncomeSource.TSHIRT,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Твоя экономика:
    # 150_000 за 24 часа, но "висит" максимум 50_000 (иначе пауза до клейма)
    rate_total: Mapped[int] = mapped_column(Integer, nullable=False, default=150_000)
    cycle_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=86_400)
    cap_unclaimed: Mapped[int] = mapped_column(Integer, nullable=False, default=50_000)

    cycle_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Для "ленивого" начисления при заходе / status / claim (рекомендую)
    last_calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Сколько накопилось и не забрано (0..cap_unclaimed)
    accrued_unclaimed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Статистика
    total_claimed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_claim_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user = relationship("User", lazy="selectin")

    __table_args__ = (
        # Одна карточка одного типа на пользователя (т.е. купил футболку -> одна tshirt-card)
        UniqueConstraint("user_id", "source", name="uq_passive_income_user_source"),
        Index("ix_passive_income_user_id", "user_id"),
        Index("ix_passive_income_active", "is_active"),
    )

