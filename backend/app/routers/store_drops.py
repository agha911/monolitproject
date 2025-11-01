from __future__ import annotations
from datetime import datetime
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.models.user import User
from app.models.drop import Drop
from app.models.partner import Partner
from app.models.drop_purchase import DropPurchase
from app.crud.user import get_user

# генератор кода (оставь путь, который у тебя используется в проекте)
from app.drop_utils.codes import generate_unique_code

router = APIRouter(prefix="/api", tags=["store-drops"])

# ---------- helpers ----------

async def _get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User:
    user = await get_user(session, telegram_id=telegram_id)
    if not user:
        raise HTTPException(status_code=403, detail="User is not registered")
    return user

def _get_balance(u: User) -> int:
    if getattr(u, "total_xp", None) is not None:
        return int(u.total_xp or 0)
    if getattr(u, "score", None) is not None:
        return int(u.score or 0)
    return 0

def _set_balance(u: User, value: int) -> None:
    if hasattr(u, "total_xp"):
        u.total_xp = int(value)
    elif hasattr(u, "score"):
        u.score = int(value)
    else:
        raise HTTPException(status_code=500, detail="User balance field missing")

async def _count_supply_used(session: AsyncSession, drop_id: int) -> int:
    q = select(func.count(DropPurchase.id)).where(
        DropPurchase.drop_id == drop_id,
        DropPurchase.status != "revoked",
    )
    res = await session.execute(q)
    return int(res.scalar() or 0)

async def _count_user_used(session: AsyncSession, drop_id: int, user_id: int) -> int:
    q = select(func.count(DropPurchase.id)).where(
        DropPurchase.drop_id == drop_id,
        DropPurchase.user_id == user_id,
        DropPurchase.status != "revoked",
    )
    res = await session.execute(q)
    return int(res.scalar() or 0)

# ---------- schemas ----------

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
    partner: Optional[dict] = None
    # 🆕 персональные поля
    user_used: int = 0
    user_left: int = 0
    disabled_for_user: bool = False

class BuyDropIn(BaseModel):
    telegram_id: int
    drop_id: int

class PurchaseOut(BaseModel):
    id: int
    user_id: int
    drop_id: int
    unique_code: str
    status: Literal["active", "redeemed", "revoked"]
    created_at: datetime
    redeemed_at: Optional[datetime] = None
    drop_title: Optional[str] = None
    partner_name: Optional[str] = None
    price_coins: Optional[int] = None
    discount_percent: Optional[float] = None

# ---------- routes ----------

@router.get("/drops", response_model=list[DropOut])
async def list_drops(
    session: AsyncSession = Depends(get_async_session),
    x_telegram_user_id: Optional[int] = Header(default=None, alias="X-Telegram-User-Id"),
):
    """
    Возвращает активные дропы. Если передан X-Telegram-User-Id, добавляет персональные поля:
    user_used / user_left / disabled_for_user (учитывая per_user_limit).
    """
    now = func.now()
    q = (
        select(Drop)
        .where(
            Drop.active.is_(True),
            Drop.visible.is_(True),
            Drop.start_at <= now,
            Drop.end_at >= now,
        )
        .order_by(Drop.start_at.asc())
    )
    res = await session.execute(q)
    rows: list[Drop] = res.scalars().all()

    # Текущий пользователь (если передан заголовок)
    current_user: Optional[User] = None
    if x_telegram_user_id:
        try:
            current_user = await _get_user_by_telegram_id(session, int(x_telegram_user_id))
        except HTTPException:
            current_user = None

    out: list[DropOut] = []
    for d in rows:
        user_used = 0
        user_left = 0
        disabled_for_user = False

        if current_user and (d.per_user_limit or 0) > 0:
            user_used = await _count_user_used(session, d.id, current_user.id)
            user_left = max(0, int(d.per_user_limit) - user_used)
            disabled_for_user = (user_left == 0)

        out.append(
            DropOut(
                id=d.id,
                partner_id=d.partner_id,
                title=d.title,
                discount_percent=float(d.discount_percent),
                start_at=d.start_at,
                end_at=d.end_at,
                price_coins=int(d.price_coins or 0),
                per_user_limit=int(d.per_user_limit or 0),
                total_supply=int(d.total_supply) if d.total_supply is not None else None,
                active=bool(d.active),
                visible=bool(d.visible),
                partner={"id": d.partner.id, "name": d.partner.name, "slug": d.partner.slug} if d.partner else None,
                user_used=user_used,
                user_left=user_left,
                disabled_for_user=disabled_for_user,
            )
        )
    return out

@router.post("/drops/buy", response_model=PurchaseOut)
async def buy_drop(payload: BuyDropIn, session: AsyncSession = Depends(get_async_session)):
    user: User = await _get_user_by_telegram_id(session, payload.telegram_id)

    # блокировка строки дропа для проверки лимитов/остатков
    qd = select(Drop).where(Drop.id == payload.drop_id).with_for_update()
    res = await session.execute(qd)
    drop = res.scalar_one_or_none()
    if not drop:
        raise HTTPException(status_code=404, detail="drop_not_found")

    now_row = await session.execute(select(func.now()))
    now = now_row.scalar()
    if not drop.active or not drop.visible:
        raise HTTPException(status_code=400, detail="drop_inactive")
    if not (drop.start_at <= now <= drop.end_at):
        raise HTTPException(status_code=400, detail="drop_out_of_window")

    # общий лимит
    if drop.total_supply is not None:
        used = await _count_supply_used(session, drop.id)
        if used >= int(drop.total_supply):
            raise HTTPException(status_code=400, detail="drop_total_supply_reached")

    # персональный лимит
    if int(drop.per_user_limit or 0) > 0:
        used_user = await _count_user_used(session, drop.id, user.id)
        if used_user >= int(drop.per_user_limit):
            raise HTTPException(status_code=400, detail="drop_user_limit_reached")

    # списываем монеты
    price = int(drop.price_coins or 0)
    if price > 0:
        bal = _get_balance(user)
        if bal < price:
            raise HTTPException(status_code=400, detail="not_enough_coins")
        _set_balance(user, bal - price)

    # создаём покупку + уникальный код
    purchase = None
    for _ in range(5):
        code = generate_unique_code(prefix="GAP", size=10)
        try:
            purchase = DropPurchase(
                user_id=user.id,
                drop_id=drop.id,
                unique_code=code,
                status="active",
            )
            session.add(purchase)
            await session.flush()
            break
        except IntegrityError:
            await session.rollback()
            continue
    if not purchase:
        raise HTTPException(status_code=500, detail="code_generation_conflict")

    await session.commit()
    await session.refresh(purchase)
    await session.refresh(drop)

    return PurchaseOut(
        id=purchase.id,
        user_id=purchase.user_id,
        drop_id=purchase.drop_id,
        unique_code=purchase.unique_code,
        status=purchase.status,  # type: ignore
        created_at=purchase.created_at,
        redeemed_at=purchase.redeemed_at,
        drop_title=drop.title,
        partner_name=drop.partner.name if drop.partner else None,
        price_coins=int(drop.price_coins or 0),
        discount_percent=float(drop.discount_percent),
    )
