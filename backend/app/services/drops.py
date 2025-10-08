# app/services/drops.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.drop import Drop
from app.models.drop_purchase import DropPurchase
from app.models.user import User
from app.crud.drop_purchases import (
    count_total_supply_used,
    count_user_used,
    create_purchase_raw,
    get_purchase_by_code,
)
from app.drop_utils.codes import generate_unique_code


class DropBuyError(Exception):
    pass


async def _get_drop_for_update(session: AsyncSession, drop_id: int) -> Optional[Drop]:
    """Заблокировать строку дропа на время операции (для корректного подсчёта supply)."""
    stmt = select(Drop).where(Drop.id == drop_id).with_for_update()
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def _deduct_user_score(session: AsyncSession, user_id: int, amount: int) -> None:
    """Списать монеты из поля `User.score` (баланс игры)."""
    if amount <= 0:
        return
    res = await session.execute(select(User).where(User.id == user_id).with_for_update())
    user = res.scalar_one_or_none()
    if not user:
        raise DropBuyError("user_not_found")

    current = int(user.score or 0)
    if current < amount:
        raise DropBuyError("not_enough_coins")

    user.score = current - amount  # SQLAlchemy сам выполнит UPDATE при flush/commit


async def buy_drop(session: AsyncSession, *, user_id: int, drop_id: int) -> DropPurchase:
    """
    Покупка дропа с проверками:
      - дроп активен, видим, окно дат ок
      - не превышен total_supply и per_user_limit
      - списываем score пользователя
      - создаём unique_code (ретраи при конфликте)
    """
    # 1) читаем дроп под блокировкой
    drop = await _get_drop_for_update(session, drop_id)
    if not drop:
        raise DropBuyError("drop_not_found")

    # 2) валидации
    if not drop.active or not drop.visible:
        raise DropBuyError("drop_inactive")

    res = await session.execute(select(func.now()))
    now = res.scalar()
    if not (drop.start_at <= now <= drop.end_at):
        raise DropBuyError("drop_out_of_window")

    # лимиты
    if drop.total_supply is not None:
        used = await count_total_supply_used(session, drop.id)
        if used >= drop.total_supply:
            raise DropBuyError("drop_total_supply_reached")

    if drop.per_user_limit and drop.per_user_limit > 0:
        used_user = await count_user_used(session, drop.id, user_id)
        if used_user >= drop.per_user_limit:
            raise DropBuyError("drop_user_limit_reached")

    # 3) списание монет (score)
    price = int(drop.price_coins or 0)
    await _deduct_user_score(session, user_id, price)

    # 4) генерация кода с ретраями при конфликте UNIQUE
    for _ in range(5):
        code = generate_unique_code(prefix="GAP", size=10)
        try:
            purchase = await create_purchase_raw(session, user_id=user_id, drop_id=drop.id, unique_code=code)
            return purchase
        except Exception as e:
            if "unique" in str(e).lower() and "unique_code" in str(e).lower():
                continue
            raise

    raise DropBuyError("code_generation_conflict")


async def redeem_by_code(session: AsyncSession, *, unique_code: str, actor_is_partner: bool = True) -> DropPurchase:
    """
    Погашение (REDEEM) кода партнёром/ботом.
    Правила простые для MVP:
      - код существует и в статусе 'active'
      - переводим в 'redeemed', выставляем redeemed_at=now()
    """
    purchase = await get_purchase_by_code(session, unique_code)
    if not purchase:
        raise DropBuyError("purchase_not_found")
    if purchase.status != "active":
        raise DropBuyError("wrong_status")

    purchase.status = "redeemed"
    purchase.redeemed_at = datetime.utcnow()
    await session.flush()
    return purchase


async def revoke_by_code(session: AsyncSession, *, unique_code: str) -> DropPurchase:
    """
    Отмена (REVOKED) кода админом/партнёром, если код ещё не погашен.
    """
    purchase = await get_purchase_by_code(session, unique_code)
    if not purchase:
        raise DropBuyError("purchase_not_found")
    if purchase.status == "redeemed":
        raise DropBuyError("already_redeemed")

    purchase.status = "revoked"
    await session.flush()
    return purchase

