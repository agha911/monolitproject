from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_current_user
from app.schemas.drops import DropWithPartnerOut, BuyDropIn, PurchaseOut
from app.crud.drops import list_drops
from app.services.drops import buy_drop, DropBuyError

router = APIRouter(prefix="/api", tags=["drops"])

@router.get("/drops", response_model=list[DropWithPartnerOut])
async def list_public_drops(
    active_only: bool = Query(True),
    visible_only: bool = Query(True),
    current_window: bool = Query(True),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    drops = await list_drops(
        session,
        only_active=active_only,
        only_visible=visible_only,
        only_current_window=current_window,
        limit=limit,
        offset=offset,
    )
    return drops

@router.post("/drops/buy", response_model=PurchaseOut, status_code=status.HTTP_201_CREATED)
async def buy_drop_endpoint(
    payload: BuyDropIn,
    session: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    try:
        async with session.begin():
            purchase = await buy_drop(session, user_id=current_user.id, drop_id=payload.drop_id)
        # обогащаем для UI
        if purchase.drop:
            purchase.drop_title = purchase.drop.title
            if purchase.drop.partner:
                purchase.partner_name = purchase.drop.partner.name
            purchase.price_coins = purchase.drop.price_coins
            purchase.discount_percent = float(purchase.drop.discount_percent)
        return purchase
    except DropBuyError as e:
        mapping = {
            "drop_not_found": (status.HTTP_404_NOT_FOUND, "Drop not found"),
            "drop_inactive": (status.HTTP_400_BAD_REQUEST, "Drop is not active"),
            "drop_out_of_window": (status.HTTP_400_BAD_REQUEST, "Drop is out of date window"),
            "drop_total_supply_reached": (status.HTTP_409_CONFLICT, "Total supply reached"),
            "drop_user_limit_reached": (status.HTTP_409_CONFLICT, "Per-user limit reached"),
            "not_enough_coins": (status.HTTP_402_PAYMENT_REQUIRED, "Not enough coins"),
            "user_not_found": (status.HTTP_404_NOT_FOUND, "User not found"),
            "user_balance_field_missing": (status.HTTP_500_INTERNAL_SERVER_ERROR, "Balance field missing"),
            "code_generation_conflict": (status.HTTP_503_SERVICE_UNAVAILABLE, "Code generation conflict, retry"),
        }
        code, msg = mapping.get(str(e), (status.HTTP_400_BAD_REQUEST, "Buy failed"))
        raise HTTPException(status_code=code, detail=msg)
