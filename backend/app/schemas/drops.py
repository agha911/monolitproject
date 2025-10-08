from __future__ import annotations
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


# ====== OUT ======

class PartnerOut(BaseModel):
    id: int
    name: str
    slug: str

    class Config:
        from_attributes = True


class DropOut(BaseModel):
    id: int
    partner_id: int
    title: str
    discount_percent: float
    start_at: datetime
    end_at: datetime
    price_coins: int
    per_user_limit: int
    total_supply: Optional[int] = None
    active: bool
    visible: bool

    class Config:
        from_attributes = True


class DropWithPartnerOut(DropOut):
    partner: PartnerOut | None = None


class PurchaseOut(BaseModel):
    id: int
    user_id: int
    drop_id: int
    unique_code: str
    status: str
    created_at: datetime
    redeemed_at: Optional[datetime] = None

    # доп.инфо для UI
    drop_title: Optional[str] = None
    partner_name: Optional[str] = None
    price_coins: Optional[int] = None
    discount_percent: Optional[float] = None

    class Config:
        from_attributes = True


class UserCardOut(BaseModel):
    username: str
    coins: int = 0
    invited_count: int = 0
    active_drops: List[PurchaseOut] = []


# ====== IN ======

class BuyDropIn(BaseModel):
    drop_id: int = Field(..., ge=1)

class PartnerRedeemIn(BaseModel):
    unique_code: str = Field(..., min_length=6, max_length=40)

class PartnerSetStatusIn(BaseModel):
    unique_code: str
    status: str  # 'active' | 'redeemed' | 'revoked'
