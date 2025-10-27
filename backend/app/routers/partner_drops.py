from __future__ import annotations
from typing import Optional, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.models.partner import Partner
from app.models.drop import Drop
from app.models.drop_purchase import DropPurchase

router = APIRouter(prefix="/api/partner", tags=["partner-drops"])

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

class PartnerListOut(BaseModel):
    purchases: list[PurchaseOut]

class PartnerCodeIn(BaseModel):
    code: str

async def _partner_by_key(session: AsyncSession, api_key: str) -> Partner:
    res = await session.execute(select(Partner).where(Partner.api_key == api_key).limit(1))
    partner = res.scalar_one_or_none()
    if not partner:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid partner key")
    return partner

@router.get("/purchases", response_model=PartnerListOut)
async def purchases(
    status_filter: Optional[str] = Query(None, pattern="^(active|redeemed|revoked)$"),
    x_partner_key: str = Header(..., alias="X-Partner-Key"),
    session: AsyncSession = Depends(get_async_session),
):
    partner = await _partner_by_key(session, x_partner_key)

    q = (
        select(DropPurchase, Drop)
        .join(Drop, Drop.id == DropPurchase.drop_id)
        .where(Drop.partner_id == partner.id)
        .order_by(DropPurchase.created_at.desc())
    )
    if status_filter:
        q = q.where(DropPurchase.status == status_filter)

    res = await session.execute(q)
    rows = res.all()

    out: list[PurchaseOut] = []
    for dp, d in rows:
        out.append(
            PurchaseOut(
                id=dp.id,
                user_id=dp.user_id,
                drop_id=dp.drop_id,
                unique_code=dp.unique_code,
                status=dp.status,  # type: ignore
                created_at=dp.created_at.isoformat(),
                redeemed_at=dp.redeemed_at.isoformat() if dp.redeemed_at else None,
                drop_title=d.title,
                partner_name=partner.name,
                price_coins=int(d.price_coins or 0),
                discount_percent=float(d.discount_percent),
            )
        )
    return PartnerListOut(purchases=out)

@router.post("/redeem", response_model=PurchaseOut)
async def redeem(
    payload: PartnerCodeIn,
    x_partner_key: str = Header(..., alias="X-Partner-Key"),
    session: AsyncSession = Depends(get_async_session),
):
    partner = await _partner_by_key(session, x_partner_key)

    q = (
        select(DropPurchase, Drop)
        .join(Drop, Drop.id == DropPurchase.drop_id)
        .where(DropPurchase.unique_code == payload.code)
        .with_for_update()
        .limit(1)
    )
    res = await session.execute(q)
    row = res.first()
    if not row:
        raise HTTPException(status_code=404, detail="purchase_not_found")

    dp: DropPurchase = row[0]
    d: Drop = row[1]
    if d.partner_id != partner.id:
        raise HTTPException(status_code=403, detail="forbidden")

    if dp.status != "active":
        raise HTTPException(status_code=400, detail="wrong_status")

    from datetime import datetime
    dp.status = "redeemed"
    dp.redeemed_at = datetime.utcnow()
    await session.commit()
    await session.refresh(dp)

    return PurchaseOut(
        id=dp.id,
        user_id=dp.user_id,
        drop_id=dp.drop_id,
        unique_code=dp.unique_code,
        status=dp.status,  # type: ignore
        created_at=dp.created_at.isoformat(),
        redeemed_at=dp.redeemed_at.isoformat() if dp.redeemed_at else None,
        drop_title=d.title,
        partner_name=partner.name,
        price_coins=int(d.price_coins or 0),
        discount_percent=float(d.discount_percent),
    )

@router.post("/revoke", response_model=PurchaseOut)
async def revoke(
    payload: PartnerCodeIn,
    x_partner_key: str = Header(..., alias="X-Partner-Key"),
    session: AsyncSession = Depends(get_async_session),
):
    partner = await _partner_by_key(session, x_partner_key)

    q = (
        select(DropPurchase, Drop)
        .join(Drop, Drop.id == DropPurchase.drop_id)
        .where(DropPurchase.unique_code == payload.code)
        .with_for_update()
        .limit(1)
    )
    res = await session.execute(q)
    row = res.first()
    if not row:
        raise HTTPException(status_code=404, detail="purchase_not_found")

    dp: DropPurchase = row[0]
    d: Drop = row[1]
    if d.partner_id != partner.id:
        raise HTTPException(status_code=403, detail="forbidden")

    if dp.status == "redeemed":
        raise HTTPException(status_code=400, detail="already_redeemed")

    dp.status = "revoked"
    await session.commit()
    await session.refresh(dp)

    return PurchaseOut(
        id=dp.id,
        user_id=dp.user_id,
        drop_id=dp.drop_id,
        unique_code=dp.unique_code,
        status=dp.status,  # type: ignore
        created_at=dp.created_at.isoformat(),
        redeemed_at=dp.redeemed_at.isoformat() if dp.redeemed_at else None,
        drop_title=d.title,
        partner_name=partner.name,
        price_coins=int(d.price_coins or 0),
        discount_percent=float(d.discount_percent),
    )
