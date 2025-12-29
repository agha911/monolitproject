from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.t_shirt import TshirtSize
from app.models.user import User

from app.crud.t_shirt_crud import (
    get_tshirt_status,
    buy_tshirt,
    claim_tshirt_passive_income,
    set_tshirt_drop_active,
    TshirtDropNotFound,
    TshirtDropInactive,
    TshirtSoldOut,
    TshirtAlreadyPurchased,
    NotEnoughGap,
    PassiveCardNotFound,
    TshirtError,
)

# ⚠️ Замени импорты под твой проект (названия могут отличаться)
from app.database import get_async_session
from app.crud.user import get_user as get_current_user


router = APIRouter(prefix="/api/shop/tshirt", tags=["Shop"])

# Стоимость футболки в $GAP (поставь реальную)
TSHIRT_PRICE_GAP = 0  # TODO: выстави цену


# -------------------------
# Schemas
# -------------------------
class TshirtStatusOut(BaseModel):
    drop_id: int
    title: str
    is_active: bool
    total_stock: int
    sold_count: int
    left: int

    sale_started_at: Optional[str] = None
    sold_out_at: Optional[str] = None

    user_has_tshirt: bool
    user_size: Optional[str] = None

    passive_is_active: Optional[bool] = None
    accrued_unclaimed: Optional[int] = None
    cap_unclaimed: Optional[int] = None
    rate_total: Optional[int] = None
    cycle_seconds: Optional[int] = None
    is_paused: Optional[bool] = None


class TshirtBuyIn(BaseModel):
    size: TshirtSize = Field(..., description="T-shirt size: S/M/L/XL/XXL")


class TshirtBuyOut(BaseModel):
    ok: bool = True
    purchase_id: int
    size: str
    price_gap: int
    left: int


class TshirtClaimOut(BaseModel):
    ok: bool = True
    claimed_amount: int


class AdminActivateIn(BaseModel):
    is_active: bool


# -------------------------
# Routes
# -------------------------
@router.get("/status", response_model=TshirtStatusOut)
async def tshirt_status(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    """
    Статус товара/карточки:
    - остаток (10 - sold_count)
    - купил ли пользователь
    - если купил: статус пассивного дохода (accrued/cap/paused)
    """
    try:
        dto = await get_tshirt_status(session=session, user_id=user.id, drop_id=1)
        return TshirtStatusOut(
            drop_id=dto.drop_id,
            title=dto.title,
            is_active=dto.is_active,
            total_stock=dto.total_stock,
            sold_count=dto.sold_count,
            left=dto.left,
            sale_started_at=dto.sale_started_at.isoformat() if dto.sale_started_at else None,
            sold_out_at=dto.sold_out_at.isoformat() if dto.sold_out_at else None,
            user_has_tshirt=dto.user_has_tshirt,
            user_size=dto.user_size,
            passive_is_active=dto.passive_is_active,
            accrued_unclaimed=dto.accrued_unclaimed,
            cap_unclaimed=dto.cap_unclaimed,
            rate_total=dto.rate_total,
            cycle_seconds=dto.cycle_seconds,
            is_paused=dto.is_paused,
        )
    except TshirtDropNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tshirt_drop_not_found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"tshirt_status_failed: {e}")


@router.post("/buy", response_model=TshirtBuyOut)
async def tshirt_buy(
    payload: TshirtBuyIn,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    """
    Покупка футболки:
    - списывает $GAP у пользователя
    - добавляет total_spent в фонд
    - фиксирует покупку (size)
    - активирует карточку пассивного дохода
    - уменьшает остаток (sold_count)
    """
    if TSHIRT_PRICE_GAP <= 0:
        raise HTTPException(status_code=500, detail="tshirt_price_not_configured")

    try:
        purchase = await buy_tshirt(
            session=session,
            user_id=user.id,
            size=payload.size,
            price_gap=TSHIRT_PRICE_GAP,
            drop_id=1,
        )

        # Чтобы вернуть left — проще запросить статус (лёгкий способ)
        dto = await get_tshirt_status(session=session, user_id=user.id, drop_id=1)

        return TshirtBuyOut(
            ok=True,
            purchase_id=purchase.id,
            size=purchase.size.value,
            price_gap=int(purchase.price_gap or 0),
            left=dto.left,
        )

    except TshirtDropInactive:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tshirt_drop_inactive")
    except TshirtSoldOut:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="tshirt_sold_out")
    except TshirtAlreadyPurchased:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="tshirt_already_purchased")
    except NotEnoughGap:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="not_enough_gap")
    except TshirtDropNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tshirt_drop_not_found")
    except TshirtError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"tshirt_buy_failed: {e}")


@router.post("/claim", response_model=TshirtClaimOut)
async def tshirt_claim(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    """
    Забрать накопленное с карточки:
    - начисляет пользователю accrued_unclaimed (<= 50k)
    - обнуляет accrued_unclaimed (снимает "паузу")
    """
    try:
        amount = await claim_tshirt_passive_income(session=session, user_id=user.id)
        return TshirtClaimOut(ok=True, claimed_amount=int(amount))
    except PassiveCardNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="passive_card_not_found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"tshirt_claim_failed: {e}")


# -------------------------
# Optional: admin toggle
# -------------------------
@router.post("/admin/activate")
async def tshirt_admin_activate(
    payload: AdminActivateIn,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
):
    """
    Опционально: включить/выключить продажу.
    Тут обычно нужна проверка роли админа (добавь сам).
    """
    # TODO: добавь проверку прав админа
    try:
        drop = await set_tshirt_drop_active(session=session, is_active=payload.is_active, drop_id=1)
        return {"ok": True, "is_active": bool(drop.is_active)}
    except TshirtDropNotFound:
        raise HTTPException(status_code=404, detail="tshirt_drop_not_found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"tshirt_admin_activate_failed: {e}")
