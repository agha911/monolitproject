from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import and_, func, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.drop import Drop


# CREATE
async def create_drop(
    session: AsyncSession,
    *,
    partner_id: int,
    title: str,
    discount_percent: float,
    start_at: datetime,
    end_at: datetime,
    price_coins: int = 0,
    per_user_limit: int = 1,
    total_supply: Optional[int] = None,
    description: Optional[str] = None,
    active: bool = False,
    visible: bool = True,
) -> Drop:
    drop = Drop(
        partner_id=partner_id,
        title=title,
        description=description,
        discount_percent=discount_percent,
        start_at=start_at,
        end_at=end_at,
        price_coins=price_coins,
        per_user_limit=per_user_limit,
        total_supply=total_supply,
        active=active,
        visible=visible,
    )
    session.add(drop)
    await session.flush()
    return drop


# READ
async def get_drop_by_id(session: AsyncSession, drop_id: int, with_partner: bool = False) -> Optional[Drop]:
    stmt = select(Drop).where(Drop.id == drop_id)
    if with_partner:
        stmt = stmt.options(selectinload(Drop.partner))
    res = await session.execute(stmt)
    return res.scalar_one_or_none()

async def list_drops(
    session: AsyncSession,
    *,
    partner_id: Optional[int] = None,
    only_active: bool = False,
    only_visible: bool = False,
    only_current_window: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> Iterable[Drop]:
    now = func.now()
    conds = []
    if partner_id is not None:
        conds.append(Drop.partner_id == partner_id)
    if only_active:
        conds.append(Drop.active.is_(True))
    if only_visible:
        conds.append(Drop.visible.is_(True))
    if only_current_window:
        conds.append(and_(Drop.start_at <= now, Drop.end_at >= now))

    stmt = select(Drop).where(and_(*conds)) if conds else select(Drop)
    stmt = stmt.order_by(Drop.id.desc()).limit(limit).offset(offset)
    res = await session.execute(stmt)
    return res.scalars().all()


# UPDATE
async def update_drop(
    session: AsyncSession,
    drop_id: int,
    **fields,
) -> Optional[Drop]:
    clean = {k: v for k, v in fields.items() if v is not None}
    if not clean:
        return await get_drop_by_id(session, drop_id)
    stmt = (
        update(Drop)
        .where(Drop.id == drop_id)
        .values(**clean)
        .returning(Drop)
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


# DELETE (осторожно: если есть покупки ON DELETE RESTRICT в БД)
async def delete_drop(session: AsyncSession, drop_id: int) -> int:
    res = await session.execute(delete(Drop).where(Drop.id == drop_id))
    return res.rowcount or 0
