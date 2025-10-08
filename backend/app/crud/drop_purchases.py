from __future__ import annotations

from typing import Iterable, Optional, Tuple

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.drop_purchase import DropPurchase
from app.models.drop import Drop


# READ
async def get_purchase_by_id(session: AsyncSession, purchase_id: int) -> Optional[DropPurchase]:
    res = await session.execute(
        select(DropPurchase)
        .where(DropPurchase.id == purchase_id)
        .options(selectinload(DropPurchase.drop))
    )
    return res.scalar_one_or_none()

async def get_purchase_by_code(session: AsyncSession, unique_code: str) -> Optional[DropPurchase]:
    res = await session.execute(
        select(DropPurchase)
        .where(DropPurchase.unique_code == unique_code)
        .options(selectinload(DropPurchase.drop))
    )
    return res.scalar_one_or_none()

async def list_purchases_by_user(
    session: AsyncSession, user_id: int, *, status: Optional[str] = None, limit: int = 50, offset: int = 0
) -> Iterable[DropPurchase]:
    conds = [DropPurchase.user_id == user_id]
    if status:
        conds.append(DropPurchase.status == status)
    res = await session.execute(
        select(DropPurchase)
        .where(and_(*conds))
        .order_by(DropPurchase.id.desc())
        .limit(limit)
        .offset(offset)
        .options(selectinload(DropPurchase.drop))
    )
    return res.scalars().all()

async def count_total_supply_used(session: AsyncSession, drop_id: int) -> int:
    # считаем активные + редимленные (revoked не учитываем в занятый supply)
    res = await session.execute(
        select(func.count()).select_from(DropPurchase).where(
            and_(DropPurchase.drop_id == drop_id, DropPurchase.status.in_(("active", "redeemed")))
        )
    )
    return int(res.scalar() or 0)

async def count_user_used(session: AsyncSession, drop_id: int, user_id: int) -> int:
    res = await session.execute(
        select(func.count()).select_from(DropPurchase).where(
            and_(
                DropPurchase.drop_id == drop_id,
                DropPurchase.user_id == user_id,
                DropPurchase.status.in_(("active", "redeemed")),
            )
        )
    )
    return int(res.scalar() or 0)


# CREATE (низкоуровневый — БЕЗ проверок лимитов/окна/активности)
async def create_purchase_raw(
    session: AsyncSession, *, user_id: int, drop_id: int, unique_code: str
) -> DropPurchase:
    purchase = DropPurchase(user_id=user_id, drop_id=drop_id, unique_code=unique_code)
    session.add(purchase)
    await session.flush()
    return purchase


# UPDATE СТАТУСА (без бизнес-проверок)
async def set_purchase_status(
    session: AsyncSession, purchase_id: int, *, new_status: str, redeemed_at=None
) -> Optional[DropPurchase]:
    stmt = (
        update(DropPurchase)
        .where(DropPurchase.id == purchase_id)
        .values(status=new_status, redeemed_at=redeemed_at)
        .returning(DropPurchase)
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()
