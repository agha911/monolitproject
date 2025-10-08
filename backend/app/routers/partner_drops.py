from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_partner_by_api_key
from app.schemas.drops import PartnerRedeemIn, PartnerSetStatusIn, PurchaseOut
from app.services.drops import redeem_by_code, revoke_by_code, DropBuyError
from app.models.partner import Partner
from app.models.drop import Drop
from app.models.drop_purchase import DropPurchase

router = APIRouter(prefix="/partner", tags=["partner"])

@router.post("/redeem", response_model=PurchaseOut)
async def partner_redeem(
    payload: PartnerRedeemIn,
    session: AsyncSession = Depends(get_db),
    partner: Partner = Depends(get_partner_by_api_key),
):
    try:
        async with session.begin():
            purchase = await redeem_by_code(session, unique_code=payload.unique_code, actor_is_partner=True)
            await session.refresh(purchase, attribute_names=["drop"])
            if not purchase.drop or purchase.drop.partner_id != partner.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Code not from your drops")

        if purchase.drop:
            purchase.drop_title = purchase.drop.title
            purchase.partner_name = partner.name
            purchase.price_coins = purchase.drop.price_coins
            purchase.discount_percent = float(purchase.drop.discount_percent)
        return purchase
    except DropBuyError as e:
        mapping = {
            "purchase_not_found": (status.HTTP_404_NOT_FOUND, "Purchase not found"),
            "wrong_status": (status.HTTP_409_CONFLICT, "Wrong status for redeem"),
        }
        code, msg = mapping.get(str(e), (status.HTTP_400_BAD_REQUEST, "Redeem failed"))
        raise HTTPException(status_code=code, detail=msg)

@router.post("/status", response_model=PurchaseOut)
async def partner_set_status(
    payload: PartnerSetStatusIn,
    session: AsyncSession = Depends(get_db),
    partner: Partner = Depends(get_partner_by_api_key),
):
    if payload.status not in ("revoked", "redeemed", "active"):
        raise HTTPException(status_code=400, detail="Unsupported status")

    res = await session.execute(
        select(DropPurchase, Drop)
        .join(Drop, Drop.id == DropPurchase.drop_id)
        .where(DropPurchase.unique_code == payload.unique_code)
        .with_for_update()
    )
    row = res.first()
    if not row:
        raise HTTPException(status_code=404, detail="Purchase not found")
    purchase, drop = row[0], row[1]
    if drop.partner_id != partner.id:
        raise HTTPException(status_code=403, detail="Purchase not from your drops")

    async with session.begin():
        if payload.status == "revoked":
            purchase = await revoke_by_code(session, unique_code=payload.unique_code)
        elif payload.status == "redeemed":
            purchase = await redeem_by_code(session, unique_code=payload.unique_code)
        elif payload.status == "active":
            if purchase.status == "redeemed":
                raise HTTPException(status_code=409, detail="Already redeemed")
            purchase.status = "active"

    await session.refresh(purchase, attribute_names=["drop"])
    purchase.drop_title = purchase.drop.title if purchase.drop else None
    purchase.partner_name = partner.name
    purchase.price_coins = purchase.drop.price_coins if purchase.drop else None
    purchase.discount_percent = float(purchase.drop.discount_percent) if purchase.drop else None
    return purchase

@router.get("/purchases", response_model=list[PurchaseOut])
async def partner_purchases(
    drop_id: int = Query(..., ge=1),
    status_filter: str | None = Query(None, pattern="^(active|redeemed|revoked)$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
    partner: Partner = Depends(get_partner_by_api_key),
):
    drop = await session.get(Drop, drop_id)
    if not drop or drop.partner_id != partner.id:
        raise HTTPException(status_code=404, detail="Drop not found")

    conds = [DropPurchase.drop_id == drop_id]
    if status_filter:
        conds.append(DropPurchase.status == status_filter)

    res = await session.execute(
        select(DropPurchase)
        .where(and_(*conds))
        .order_by(DropPurchase.id.desc())
        .limit(limit).offset(offset)
    )
    items = res.scalars().all()

    out: list[PurchaseOut] = []
    for p in items:
        await session.refresh(p, attribute_names=["drop"])
        out.append(
            PurchaseOut(
                id=p.id, user_id=p.user_id, drop_id=p.drop_id, unique_code=p.unique_code,
                status=p.status, created_at=p.created_at, redeemed_at=p.redeemed_at,
                drop_title=p.drop.title if p.drop else None,
                partner_name=partner.name,
                price_coins=p.drop.price_coins if p.drop else None,
                discount_percent=float(p.drop.discount_percent) if p.drop else None,
            )
        )
    return out
