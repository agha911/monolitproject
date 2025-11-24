# app/crud/dao.py

from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dao import ArtWork, DaoProposal, DaoUserVotingPower, DaoOption, DaoVote
from app.models.user import User


# ─────────────────────────
# ArtWork
# ─────────────────────────

async def create_art_work(
    session: AsyncSession,
    *,
    external_id: Optional[str] = None,
    title: str,
    image_url: Optional[str] = None,
    author_telegram_id: Optional[int] = None,
    meta: Optional[dict] = None,
) -> ArtWork:
    """
    Базовый метод для создания арт-работы (если будем заводить их через админку/скрипт).
    """
    art = ArtWork(
      external_id=external_id,
      title=title,
      image_url=image_url,
      author_telegram_id=author_telegram_id,
      meta=meta or {},
    )
    session.add(art)
    await session.flush()
    return art


async def get_art_work(session: AsyncSession, art_id: int) -> Optional[ArtWork]:
    res = await session.execute(
        select(ArtWork).where(ArtWork.id == art_id)
    )
    return res.scalar_one_or_none()


async def list_art_works(
    session: AsyncSession,
    *,
    limit: int = 100,
    offset: int = 0,
) -> Sequence[ArtWork]:
    stmt = (
        select(ArtWork)
        .order_by(ArtWork.id.asc())
        .limit(limit)
        .offset(offset)
    )
    res = await session.execute(stmt)
    return res.scalars().all()


# ─────────────────────────
# DaoProposal
# ─────────────────────────

async def create_proposal(
    session: AsyncSession,
    *,
    title: str,
    description: str,
    starts_at: datetime,
    ends_at: datetime,
    snapshot_at: Optional[datetime] = None,
    is_active: bool = True,
) -> DaoProposal:
    """
    Создать новое голосование.
    snapshot_at — пока просто поле, чтобы можно было на него опираться в будущем,
    сейчас логика "лимита по монетам" будет смотреть на текущий total_xp пользователя.
    """
    prop = DaoProposal(
        title=title,
        description=description,
        starts_at=starts_at,
        ends_at=ends_at,
        snapshot_at=snapshot_at,
        is_active=is_active,
    )
    session.add(prop)
    await session.flush()
    return prop


async def get_proposal(
    session: AsyncSession,
    proposal_id: int,
) -> Optional[DaoProposal]:
    res = await session.execute(
        select(DaoProposal).where(DaoProposal.id == proposal_id)
    )
    return res.scalar_one_or_none()


async def list_active_proposals(
    session: AsyncSession,
    *,
    now_utc: Optional[datetime] = None,
) -> Sequence[DaoProposal]:
    """
    Список активных голосований: is_active = true и текущее время в окне [starts_at, ends_at].
    """
    if now_utc is None:
        now_utc = datetime.utcnow()

    stmt = (
        select(DaoProposal)
        .where(
            DaoProposal.is_active.is_(True),
            DaoProposal.starts_at <= now_utc,
            DaoProposal.ends_at >= now_utc,
        )
        .order_by(DaoProposal.starts_at.desc())
    )
    res = await session.execute(stmt)
    return res.scalars().all()


# ─────────────────────────
# DaoOption
# ─────────────────────────

async def add_option_for_art_work(
    session: AsyncSession,
    *,
    proposal_id: int,
    art_work_id: int,
    label: Optional[str] = None,
) -> DaoOption:
    """
    Привязать арт-работу к голосованию как вариант.
    Label можно использовать для кастомного текста (например, короткий тайтл),
    но основную визуализацию будем брать из ArtWork.
    """
    opt = DaoOption(
        proposal_id=proposal_id,
        art_work_id=art_work_id,
        label=label,
    )
    session.add(opt)
    await session.flush()
    return opt


async def list_options_for_proposal(
    session: AsyncSession,
    proposal_id: int,
) -> Sequence[DaoOption]:
    stmt = (
        select(DaoOption)
        .where(DaoOption.proposal_id == proposal_id)
        .order_by(DaoOption.id.asc())
    )
    res = await session.execute(stmt)
    return res.scalars().all()


async def get_option(
    session: AsyncSession,
    option_id: int,
) -> Optional[DaoOption]:
    res = await session.execute(
        select(DaoOption).where(DaoOption.id == option_id)
    )
    return res.scalar_one_or_none()


# ─────────────────────────
# Votes
# ─────────────────────────

async def get_user_vote_total_weight(
    session: AsyncSession,
    *,
    proposal_id: int,
    user_id: int,
) -> int:
    """
    Сколько "веса" пользователь уже раскидал по этому голосованию (сумма weight по всем вариантам).
    Используется для проверки лимита: sum(weight) <= total_xp пользователя.
    """
    stmt = (
        select(func.coalesce(func.sum(DaoVote.weight), 0))
        .where(
            DaoVote.proposal_id == proposal_id,
            DaoVote.user_id == user_id,
        )
    )
    res = await session.execute(stmt)
    value = res.scalar()
    return int(value or 0)


async def get_proposal_results(
    session: AsyncSession,
    proposal_id: int,
):
    """
    Агрегированные результаты по голосам.
    Возвращает список словарей:
    {
      "option_id": ...,
      "art_work_id": ...,
      "label": ...,
      "total_weight": ...,
      "votes_count": ...,
    }
    """
    stmt = (
        select(
            DaoOption.id.label("option_id"),
            DaoOption.art_work_id.label("art_work_id"),
            DaoOption.label.label("label"),
            func.coalesce(func.sum(DaoVote.weight), 0).label("total_weight"),
            func.count(DaoVote.id).label("votes_count"),
        )
        .outerjoin(DaoVote, DaoVote.option_id == DaoOption.id)
        .where(DaoOption.proposal_id == proposal_id)
        .group_by(DaoOption.id)
        .order_by(func.coalesce(func.sum(DaoVote.weight), 0).desc())
    )
    res = await session.execute(stmt)
    rows = res.all()

    return [
        {
            "option_id": r.option_id,
            "art_work_id": r.art_work_id,
            "label": r.label,
            "total_weight": int(r.total_weight or 0),
            "votes_count": int(r.votes_count or 0),
        }
        for r in rows
    ]


async def cast_vote(
    session: AsyncSession,
    *,
    proposal: DaoProposal,
    option: DaoOption,
    user: User,
    weight: int,
    effective_balance: int,
) -> DaoVote:
    """
    Записать голос пользователя за конкретную опцию.

    ✓ Проверяем, что вес > 0
    ✓ Смотрим, сколько пользователь уже потратил голосов по ЭТОМУ proposal (кроме этой опции)
    ✓ Не даём превысить ЗАФИКСИРОВАННЫЙ effective_balance (а не текущий total_xp)
    ✓ Либо создаём новую запись DaoVote, либо обновляем существующую
    """

    w = int(weight)
    if w <= 0:
        raise ValueError("weight_must_be_positive")

    # ⚠️ ВАЖНО: больше не берём user.total_xp, используем зафиксированный effective_balance
    user_balance = int(effective_balance or 0)

    # Сколько уже потрачено на другие опции (без этой)
    used_other = await session.scalar(
        select(func.coalesce(func.sum(DaoVote.weight), 0)).where(
            DaoVote.proposal_id == proposal.id,
            DaoVote.user_id == user.id,
            DaoVote.option_id != option.id,
        )
    )
    used_other = int(used_other or 0)

    # Проверка лимита относительно зафиксированного баланса
    if used_other + w > user_balance:
        raise ValueError("insufficient_balance")

    # Пытаемся найти существующий голос по этой опции
    existing_vote = await session.scalar(
        select(DaoVote).where(
            DaoVote.proposal_id == proposal.id,
            DaoVote.user_id == user.id,
            DaoVote.option_id == option.id,
        )
    )

    now = datetime.utcnow()

    if existing_vote:
        existing_vote.weight = w
        vote = existing_vote
    else:
        vote = DaoVote(
            proposal_id=proposal.id,
            user_id=user.id,
            option_id=option.id,
            weight=w,
            created_at=now,
        )
        session.add(vote)

    return vote


async def get_user_voting_power_row(
    session: AsyncSession,
    *,
    user_id: int,
    proposal_id: int,
) -> Optional[DaoUserVotingPower]:
    """
    Вернуть запись voting power по (user, proposal), если уже существует.
    """
    stmt = (
        select(DaoUserVotingPower)
        .where(
            DaoUserVotingPower.user_id == user_id,
            DaoUserVotingPower.proposal_id == proposal_id,
        )
        .limit(1)
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def get_or_create_user_voting_power(
    session: AsyncSession,
    *,
    user_id: int,
    proposal_id: int,
    current_balance: int,
) -> DaoUserVotingPower:
    """
    Если для (user, proposal) ещё нет записи — создаём её
    с base_balance = current_balance.

    Если уже есть — просто возвращаем существующую.
    """
    row = await get_user_voting_power_row(
        session,
        user_id=user_id,
        proposal_id=proposal_id,
    )
    if row:
        return row

    row = DaoUserVotingPower(
        user_id=user_id,
        proposal_id=proposal_id,
        base_balance=int(current_balance),
    )
    session.add(row)
    # flush, чтобы id и значения точно записались в текущей транзакции
    await session.flush()
    return row


async def get_user_effective_voting_balance(
    session: AsyncSession,
    *,
    user_id: int,
    proposal_id: int,
    current_balance: int,
) -> int:
    """
    Вернуть "эффективный" баланс для голосования:
    - если пользователь голосует впервые по этому proposal → фиксируем current_balance;
    - если уже голосовал → возвращаем зафиксированный base_balance.
    """
    row = await get_or_create_user_voting_power(
        session,
        user_id=user_id,
        proposal_id=proposal_id,
        current_balance=current_balance,
    )
    return int(row.base_balance or 0)
