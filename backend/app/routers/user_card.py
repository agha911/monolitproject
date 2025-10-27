from __future__ import annotations
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.models.user import User
from app.models.drop import Drop
from app.models.partner import Partner
from app.models.drop_purchase import DropPurchase
from app.crud.user import get_user

router = APIRouter(prefix="/api", tags=["user-card"])

def _get_balance(u: User) -> int:
    if getattr(u, "total_xp", None) is not None:
        return int(u.total_xp or 0)
    if getattr(u, "score", None) is not None:
        return int(u.score or 0)
    return 0

class PurchaseOut(BaseModel):
    id: int
    user_id: int
    drop_id: int
    unique_code: str
    status: Literal["active", "redeemed", "revoked"]
    created_at: str
    redeemed_at: Optional[str] = None
    drop_title: Optional[str] = None
    partner_name: Optional[str] = None
    price_coins: Optional[int] = None
    discount_percent: Optional[float] = None

class UserCardOut(BaseModel):
    username: str
    coins: int
    invited_count: int
    active_drops: list[PurchaseOut]

@router.get("/user/card", response_model=UserCardOut)
async def user_card(
    telegram_id: int = Query(...),
    session: AsyncSession = Depends(get_async_session),
):
    user = await get_user(session, telegram_id=telegram_id)
    if not user:
        raise HTTPException(status_code=403, detail="User is not registered")

    q = (
        select(DropPurchase, Drop, Partner)
        .join(Drop, Drop.id == DropPurchase.drop_id)
        .join(Partner, Partner.id == Drop.partner_id)
        .where(
            DropPurchase.user_id == user.id,
            DropPurchase.status == "active",
        )
        .order_by(DropPurchase.created_at.desc())
    )
    res = await session.execute(q)
    rows = res.all()

    items: list[PurchaseOut] = []
    for dp, d, p in rows:
        items.append(
            PurchaseOut(
                id=dp.id,
                user_id=dp.user_id,
                drop_id=dp.drop_id,
                unique_code=dp.unique_code,
                status=dp.status,  # type: ignore
                created_at=dp.created_at.isoformat(),
                redeemed_at=dp.redeemed_at.isoformat() if dp.redeemed_at else None,
                drop_title=d.title,
                partner_name=p.name,
                price_coins=int(d.price_coins or 0),
                discount_percent=float(d.discount_percent),
            )
        )

    coins = _get_balance(user)
    invited = int(getattr(user, "invites_count", 0) or 0)

    return UserCardOut(
        username=user.username or "",
        coins=coins,
        invited_count=invited,
        active_drops=items,
    )
