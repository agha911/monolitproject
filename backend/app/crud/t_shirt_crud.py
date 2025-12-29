from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.t_shirt import (
    TshirtDrop,
    TshirtPurchase,
    TshirtSize,
    PassiveIncomeCard,
    PassiveIncomeSource,
)

# импорт твоей функции фонда
from app.crud.user import increment_total_spent


# -------------------------
# Exceptions (для роутов)
# -------------------------
class TshirtError(Exception):
    pass


class TshirtDropNotFound(TshirtError):
    pass


class TshirtDropInactive(TshirtError):
    pass


class TshirtSoldOut(TshirtError):
    pass


class TshirtAlreadyPurchased(TshirtError):
    pass


class NotEnoughGap(TshirtError):
    pass


class PassiveCardNotFound(TshirtError):
    pass


@dataclass
class TshirtStatusDTO:
    drop_id: int
    title: str
    is_active: bool
    total_stock: int
    sold_count: int
    left: int
    sale_started_at: Optional[datetime]
    sold_out_at: Optional[datetime]
    user_has_tshirt: bool
    user_size: Optional[str]

    # если у юзера есть карточка
    passive_is_active: Optional[bool] = None
    accrued_unclaimed: Optional[int] = None
    cap_unclaimed: Optional[int] = None
    rate_total: Optional[int] = None
    cycle_seconds: Optional[int] = None
    is_paused: Optional[bool] = None


# -------------------------
# Helpers
# -------------------------
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _clamp_int(v: int, lo: int, hi: int) -> int:
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


async def get_or_create_tshirt_drop(
    session: AsyncSession,
    drop_id: int = 1,
    title_default: str = "Gappick T-shirt",
    total_stock_default: int = 10,
) -> TshirtDrop:
    """
    Гарантирует, что в базе есть запись tshirt_drop (обычно id=1).
    """
    res = await session.execute(select(TshirtDrop).where(TshirtDrop.id == drop_id))
    drop = res.scalar_one_or_none()
    if drop:
        return drop

    drop = TshirtDrop(
        id=drop_id,
        title=title_default,
        total_stock=total_stock_default,
        sold_count=0,
        is_active=False,
        sale_started_at=None,
        sold_out_at=None,
    )
    session.add(drop)
    await session.commit()
    await session.refresh(drop)
    return drop


async def get_tshirt_drop(session: AsyncSession, drop_id: int = 1) -> TshirtDrop:
    res = await session.execute(select(TshirtDrop).where(TshirtDrop.id == drop_id))
    drop = res.scalar_one_or_none()
    if not drop:
        raise TshirtDropNotFound(f"TshirtDrop id={drop_id} not found")
    return drop


async def get_user_tshirt_purchase(
    session: AsyncSession,
    user_id: int,
    drop_id: int = 1,
) -> Optional[TshirtPurchase]:
    res = await session.execute(
        select(TshirtPurchase).where(
            TshirtPurchase.user_id == user_id,
            TshirtPurchase.drop_id == drop_id,
        )
    )
    return res.scalar_one_or_none()


async def get_user_passive_card(
    session: AsyncSession,
    user_id: int,
    source: PassiveIncomeSource = PassiveIncomeSource.TSHIRT,
) -> Optional[PassiveIncomeCard]:
    res = await session.execute(
        select(PassiveIncomeCard).where(
            PassiveIncomeCard.user_id == user_id,
            PassiveIncomeCard.source == source,
        )
    )
    return res.scalar_one_or_none()


# -------------------------
# Passive income расчет (ленивый)
# -------------------------
async def refresh_passive_card_accrual(
    session: AsyncSession,
    card: PassiveIncomeCard,
    now: Optional[datetime] = None,
) -> PassiveIncomeCard:
    """
    Пересчитывает accrued_unclaimed по времени с учетом cap.
    Фарм "паузится", если accrued_unclaimed достиг cap_unclaimed.
    """
    if now is None:
        now = _utcnow()

    if not card.is_active:
        return card

    # Если уже уперлись в cap — пауза (ничего не начисляем)
    if int(card.accrued_unclaimed or 0) >= int(card.cap_unclaimed or 0):
        # можно обновить last_calculated_at, но это не обязательно.
        # оставим как есть (чтобы не плодить лишних UPDATE)
        return card

    last_ts = card.last_calculated_at or card.cycle_started_at or now
    if last_ts > now:
        # странный случай (clock skew) — просто выровняем
        card.last_calculated_at = now
        await session.commit()
        await session.refresh(card)
        return card

    elapsed_sec = (now - last_ts).total_seconds()
    if elapsed_sec <= 0:
        return card

    rate_total = int(card.rate_total or 0)
    cycle_seconds = int(card.cycle_seconds or 86400)
    cap = int(card.cap_unclaimed or 0)

    if rate_total <= 0 or cycle_seconds <= 0 or cap <= 0:
        card.last_calculated_at = now
        await session.commit()
        await session.refresh(card)
        return card

    # скорость начисления в секунду
    rate_per_sec = rate_total / float(cycle_seconds)

    add_float = rate_per_sec * elapsed_sec
    add_int = int(add_float)  # монеты целые
    if add_int <= 0:
        # накопилось меньше 1 монеты — просто двигаем last_calculated_at, чтобы не копить микродельты бесконечно
        card.last_calculated_at = now
        await session.commit()
        await session.refresh(card)
        return card

    before = int(card.accrued_unclaimed or 0)
    after = _clamp_int(before + add_int, 0, cap)

    card.accrued_unclaimed = after
    card.last_calculated_at = now
    await session.commit()
    await session.refresh(card)
    return card


# -------------------------
# Status для магазина
# -------------------------
async def get_tshirt_status(
    session: AsyncSession,
    user_id: int,
    drop_id: int = 1,
) -> TshirtStatusDTO:
    drop = await get_tshirt_drop(session, drop_id=drop_id)
    left = max(int(drop.total_stock or 0) - int(drop.sold_count or 0), 0)

    purchase = await get_user_tshirt_purchase(session, user_id=user_id, drop_id=drop_id)

    dto = TshirtStatusDTO(
        drop_id=drop.id,
        title=drop.title,
        is_active=bool(drop.is_active),
        total_stock=int(drop.total_stock or 0),
        sold_count=int(drop.sold_count or 0),
        left=left,
        sale_started_at=drop.sale_started_at,
        sold_out_at=drop.sold_out_at,
        user_has_tshirt=bool(purchase),
        user_size=(purchase.size.value if purchase else None),
    )

    if purchase:
        card = await get_user_passive_card(session, user_id=user_id, source=PassiveIncomeSource.TSHIRT)
        if card:
            card = await refresh_passive_card_accrual(session, card)
            dto.passive_is_active = bool(card.is_active)
            dto.accrued_unclaimed = int(card.accrued_unclaimed or 0)
            dto.cap_unclaimed = int(card.cap_unclaimed or 0)
            dto.rate_total = int(card.rate_total or 0)
            dto.cycle_seconds = int(card.cycle_seconds or 0)
            dto.is_paused = dto.accrued_unclaimed >= dto.cap_unclaimed

    return dto


# -------------------------
# Buy tshirt (лимит 10, размер, списание у юзера, фонд, карточка)
# -------------------------
async def buy_tshirt(
    session: AsyncSession,
    user_id: int,
    size: TshirtSize,
    price_gap: int,
    drop_id: int = 1,
) -> TshirtPurchase:
    """
    Покупка футболки:
    - проверяем активность
    - блокируем строку дропа (FOR UPDATE)
    - проверяем наличие
    - проверяем "не купил ли уже"
    - списываем GAP у пользователя
    - начисляем в фонд (increment_total_spent)
    - создаём purchase
    - создаём/активируем passive_income_card
    - обновляем sold_count, sold_out_at
    """
    if price_gap <= 0:
        raise ValueError("price_gap must be > 0")

    now = _utcnow()

    # 1) Берём user
    res_u = await session.execute(select(User).where(User.id == user_id))
    user = res_u.scalar_one_or_none()
    if not user:
        raise TshirtError(f"User id={user_id} not found")

    # 2) Лочим дроп на время покупки (защита от 11-й покупки)
    res_d = await session.execute(
        select(TshirtDrop).where(TshirtDrop.id == drop_id).with_for_update()
    )
    drop = res_d.scalar_one_or_none()
    if not drop:
        raise TshirtDropNotFound(f"TshirtDrop id={drop_id} not found")

    if not drop.is_active:
        raise TshirtDropInactive("Tshirt drop is not active")

    if int(drop.sold_count or 0) >= int(drop.total_stock or 0):
        raise TshirtSoldOut("Tshirt is sold out")

    # 3) Уже покупал?
    existing = await get_user_tshirt_purchase(session, user_id=user_id, drop_id=drop_id)
    if existing:
        raise TshirtAlreadyPurchased("User already purchased tshirt")

    # 4) Фиксируем старт продаж, если не был зафиксирован
    if drop.sale_started_at is None:
        drop.sale_started_at = now

    # 5) Проверка баланса и списание
    user_balance = int(getattr(user, "total_xp", 0) or 0)
    if user_balance < price_gap:
        raise NotEnoughGap("Not enough $GAP")

    setattr(user, "total_xp", user_balance - price_gap)

    # 6) Зачисляем в фонд
    # ВАЖНО: твоя increment_total_spent делает session.commit().
    # Идеально — убрать commit из increment_total_spent и коммитить единоразово тут.
    await increment_total_spent(session, price_gap)

    # 7) Создаём purchase
    purchase = TshirtPurchase(
        user_id=user_id,
        drop_id=drop_id,
        size=size,
        price_gap=price_gap,
        fund_amount=price_gap,
        status="confirmed",
        purchased_at=now,
    )
    session.add(purchase)

    # 8) Создаём/активируем карточку пассивного дохода
    card = await get_user_passive_card(session, user_id=user_id, source=PassiveIncomeSource.TSHIRT)
    if not card:
        card = PassiveIncomeCard(
            user_id=user_id,
            source=PassiveIncomeSource.TSHIRT,
            is_active=True,
            cycle_started_at=now,
            last_calculated_at=now,
            accrued_unclaimed=0,
            total_claimed=0,
            last_claim_at=None,
        )
        session.add(card)
    else:
        card.is_active = True
        # перезапускаем цикл с момента покупки
        card.cycle_started_at = now
        card.last_calculated_at = now
        card.accrued_unclaimed = 0
        card.last_claim_at = None

    # 9) Обновляем sold_count
    drop.sold_count = int(drop.sold_count or 0) + 1
    if int(drop.sold_count) >= int(drop.total_stock or 0) and drop.sold_out_at is None:
        drop.sold_out_at = now

    # 10) Коммит покупки
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        # если одновременно купили и упёрлись в unique(user_id, drop_id)
        raise TshirtAlreadyPurchased("User already purchased tshirt (race condition)")

    await session.refresh(purchase)
    return purchase


# -------------------------
# Claim: забрать накопленное (до 50k), начислить юзеру
# -------------------------
async def claim_tshirt_passive_income(
    session: AsyncSession,
    user_id: int,
) -> int:
    """
    1) Обновить accrued_unclaimed (refresh)
    2) Если 0 — вернуть 0
    3) Добавить в user.total_xp
    4) Обнулить accrued_unclaimed
    5) Обновить last_claim_at, total_claimed, last_calculated_at
    """
    now = _utcnow()

    res_u = await session.execute(select(User).where(User.id == user_id))
    user = res_u.scalar_one_or_none()
    if not user:
        raise TshirtError(f"User id={user_id} not found")

    card = await get_user_passive_card(session, user_id=user_id, source=PassiveIncomeSource.TSHIRT)
    if not card or not card.is_active:
        raise PassiveCardNotFound("Passive income card not found or inactive")

    card = await refresh_passive_card_accrual(session, card, now=now)

    amount = int(card.accrued_unclaimed or 0)
    if amount <= 0:
        return 0

    # начисляем юзеру
    user_balance = int(getattr(user, "total_xp", 0) or 0)
    setattr(user, "total_xp", user_balance + amount)

    # обнуляем накопленное и снимаем паузу
    card.accrued_unclaimed = 0
    card.total_claimed = int(card.total_claimed or 0) + amount
    card.last_claim_at = now
    card.last_calculated_at = now  # стартуем новый отсчет для следующего накопления

    await session.commit()
    return amount


# -------------------------
# Админские CRUD (опционально)
# -------------------------
async def set_tshirt_drop_active(
    session: AsyncSession,
    is_active: bool,
    drop_id: int = 1,
) -> TshirtDrop:
    drop = await get_tshirt_drop(session, drop_id=drop_id)
    drop.is_active = bool(is_active)
    # если включаем и старт еще не фиксирован — можно зафиксировать старт
    if drop.is_active and drop.sale_started_at is None:
        drop.sale_started_at = _utcnow()

    await session.commit()
    await session.refresh(drop)
    return drop


async def reset_tshirt_drop(
    session: AsyncSession,
    drop_id: int = 1,
    total_stock: int = 10,
) -> TshirtDrop:
    """
    Осторожно: для тестов/админки. Сбрасывает счётчики дропа.
    Покупки и карточки НЕ трогает.
    """
    drop = await get_tshirt_drop(session, drop_id=drop_id)
    drop.total_stock = int(total_stock)
    drop.sold_count = 0
    drop.sale_started_at = None
    drop.sold_out_at = None
    await session.commit()
    await session.refresh(drop)
    return drop
