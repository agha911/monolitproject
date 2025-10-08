from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_current_user
from app.schemas.drops import UserCardOut, PurchaseOut
from app.models.user import User
from app.models.drop_purchase import DropPurchase
from app.models.drop import Drop
from app.models.partner import Partner

router = APIRouter(prefix="/api", tags=["user-card"])


async def _get_invited_count(session: AsyncSession, user_id: int) -> int:
    """
    Реальный подсчет приглашённых: COUNT(*) пользователей, у которых invited_by = current_user.id
    """
    res = await session.execute(
        select(func.count()).select_from(User).where(User.invited_by == user_id)
    )
    return int(res.scalar() or 0)


@router.get("/user/card", response_model=UserCardOut)
async def get_user_card(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    username = current_user.username or ""
    coins = int(current_user.score or 0)  # баланс берём из поля score

    invited_count = await _get_invited_count(session, current_user.id)

    res = await session.execute(
        select(
            DropPurchase.id,
            DropPurchase.user_id,
            DropPurchase.drop_id,
            DropPurchase.unique_code,
            DropPurchase.status,
            DropPurchase.created_at,
            DropPurchase.redeemed_at,
            Drop.title.label("drop_title"),
            Drop.price_coins.label("price_coins"),
            Drop.discount_percent.label("discount_percent"),
            Partner.name.label("partner_name"),
        )
        .join(Drop, Drop.id == DropPurchase.drop_id)
        .join(Partner, Partner.id == Drop.partner_id)
        .where(DropPurchase.user_id == current_user.id, DropPurchase.status == "active")
        .order_by(DropPurchase.id.desc())
    )
    rows = res.all()
    active_drops: list[PurchaseOut] = [
        PurchaseOut(
            id=r.id, user_id=r.user_id, drop_id=r.drop_id, unique_code=r.unique_code,
            status=r.status, created_at=r.created_at, redeemed_at=r.redeemed_at,
            drop_title=r.drop_title, partner_name=r.partner_name,
            price_coins=r.price_coins,
            discount_percent=float(r.discount_percent) if r.discount_percent is not None else None,
        )
        for r in rows
    ]

    return UserCardOut(
        username=username or f"id:{current_user.id}",
        coins=coins,
        invited_count=invited_count,
        active_drops=active_drops,
    )
