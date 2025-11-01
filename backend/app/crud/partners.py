# app/crud/partners.py
from __future__ import annotations
from typing import Optional, List, Dict, Any

from sqlalchemy import select, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.partner import Partner


# ───────────────── basic getters ─────────────────

async def get_partner_by_id(session: AsyncSession, partner_id: int) -> Optional[Partner]:
    res = await session.execute(select(Partner).where(Partner.id == partner_id))
    return res.scalar_one_or_none()


async def get_partner_by_slug(session: AsyncSession, slug: str) -> Optional[Partner]:
    res = await session.execute(select(Partner).where(Partner.slug == slug))
    return res.scalar_one_or_none()


async def get_partner_balance(session: AsyncSession, partner_id: int) -> Optional[int]:
    res = await session.execute(select(Partner.partner_balance).where(Partner.id == partner_id))
    val = res.scalar()
    return None if val is None else int(val)


# ───────────────── increment balance (safe) ─────────────────
# amount может быть отрицательным (возвраты/коррекции). Если нужно запретить отрицательные — проверьте тут.

async def increment_partner_balance(session: AsyncSession, partner_id: int, amount: int) -> int:
    """
    Атомарное увеличение (или уменьшение) баланса партнёра.
    Возвращает новое значение баланса.
    """
    # блокируем строку на время операции (FOR UPDATE) — чтобы не было гонок при одновременных покупках
    res = await session.execute(
        select(Partner).where(Partner.id == partner_id).with_for_update()
    )
    partner = res.scalar_one_or_none()
    if not partner:
        raise ValueError("partner_not_found")

    current = int(partner.partner_balance or 0)
    partner.partner_balance = current + int(amount or 0)
    await session.flush()
    return int(partner.partner_balance)


# ───────────────── listing ─────────────────

async def list_partners(session: AsyncSession, *, limit: int = 100, offset: int = 0) -> List[Partner]:
    q = (
        select(Partner)
        .order_by(desc(Partner.partner_balance), Partner.id.asc())
        .limit(limit)
        .offset(offset)
    )
    res = await session.execute(q)
    return list(res.scalars().all())


async def list_partner_balances(
    session: AsyncSession,
    *,
    limit: int = 100,
    offset: int = 0,
    order: str = "desc",   # "desc" | "asc"
) -> List[Dict[str, Any]]:
    """
    Упрощённый список балансов для админ/дашбордов.
    Возвращает массив словарей: {id, name, slug, partner_balance}
    """
    order_by = desc(Partner.partner_balance) if order.lower() == "desc" else asc(Partner.partner_balance)
    q = (
        select(Partner.id, Partner.name, Partner.slug, Partner.partner_balance)
        .order_by(order_by, Partner.id.asc())
        .limit(limit)
        .offset(offset)
    )
    res = await session.execute(q)
    rows = res.fetchall()
    return [
        {
            "id": int(r.id),
            "name": r.name,
            "slug": r.slug,
            "partner_balance": int(r.partner_balance or 0),
        }
        for r in rows
    ]
