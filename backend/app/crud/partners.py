from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.partner import Partner


# CREATE
async def create_partner(
    session: AsyncSession,
    *,
    name: str,
    slug: str,
    tg_username: Optional[str] = None,
    tg_user_id: Optional[int] = None,
    api_key: Optional[str] = None,
) -> Partner:
    partner = Partner(
        name=name,
        slug=slug,
        tg_username=tg_username,
        tg_user_id=tg_user_id,
        api_key=api_key,
    )
    session.add(partner)
    await session.flush()
    return partner


# READ
async def get_partner_by_id(session: AsyncSession, partner_id: int) -> Optional[Partner]:
    res = await session.execute(select(Partner).where(Partner.id == partner_id))
    return res.scalar_one_or_none()

async def get_partner_by_slug(session: AsyncSession, slug: str) -> Optional[Partner]:
    res = await session.execute(select(Partner).where(Partner.slug == slug))
    return res.scalar_one_or_none()

async def list_partners(session: AsyncSession, limit: int = 50, offset: int = 0) -> Iterable[Partner]:
    res = await session.execute(
        select(Partner).order_by(Partner.id.desc()).limit(limit).offset(offset)
    )
    return res.scalars().all()


# UPDATE
async def update_partner(
    session: AsyncSession,
    partner_id: int,
    *,
    name: Optional[str] = None,
    slug: Optional[str] = None,
    tg_username: Optional[str] = None,
    tg_user_id: Optional[int] = None,
    api_key: Optional[str] = None,
) -> Optional[Partner]:
    stmt = (
        update(Partner)
        .where(Partner.id == partner_id)
        .values(
            **{
                k: v
                for k, v in dict(
                    name=name,
                    slug=slug,
                    tg_username=tg_username,
                    tg_user_id=tg_user_id,
                    api_key=api_key,
                ).items()
                if v is not None
            }
        )
        .returning(Partner)
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


# DELETE
async def delete_partner(session: AsyncSession, partner_id: int) -> int:
    res = await session.execute(delete(Partner).where(Partner.id == partner_id))
    return res.rowcount or 0
