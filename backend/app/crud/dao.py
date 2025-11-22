# app/crud/dao.py

from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dao import ArtWork, DaoProposal, DaoOption, DaoVote
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
) -> DaoVote | None:
    """
    Устанавливает голос пользователя за КОНКРЕТНУЮ опцию.

    ВАЖНО:
      - `weight` трактуем как *конечный вес* по этой опции (а не дельту).
      - На уровне БД есть UNIQUE(proposal_id, user_id, option_id),
        поэтому мы делаем upsert: update / insert / delete.

    Правила:
      - weight < 0 → ValueError("weight_must_be_non_negative")
      - sum(weights по другим опциям) + weight <= user.total_xp,
        иначе ValueError("not_enough_balance")
      - если weight == 0 → удаляем голос по этой опции (если был).
    """
    if weight < 0:
        raise ValueError("weight_must_be_non_negative")

    user_id = int(user.id)
    proposal_id = int(proposal.id)
    option_id = int(option.id)

    # Загружаем ВСЕ голоса пользователя по этому предложению
    res = await session.execute(
        select(DaoVote).where(
            DaoVote.proposal_id == proposal_id,
            DaoVote.user_id == user_id,
        )
    )
    existing_votes = list(res.scalars())

    # Находим голос именно по этой опции (если есть)
    vote_for_option: DaoVote | None = None
    other_total = 0

    for v in existing_votes:
        if v.option_id == option_id:
            vote_for_option = v
        else:
            other_total += int(v.weight or 0)

    # Проверяем лимит: остальные голоса + новый weight по этой опции
    # не должны превышать текущий total_xp пользователя
    total_xp = int(user.total_xp or 0)
    if other_total + weight > total_xp:
        raise ValueError("not_enough_balance")

    # Если вес 0 — удаляем голос по этой опции (если был) и выходим
    if weight == 0:
        if vote_for_option is not None:
            await session.delete(vote_for_option)
        return None

    # Если голос по опции уже есть — обновляем weight
    if vote_for_option is not None:
        vote_for_option.weight = int(weight)
        # created_at можно не трогать — оставить момент первого голосования
        # или, если хочешь, обновить:
        # vote_for_option.created_at = datetime.utcnow()
        return vote_for_option

    # Иначе — создаём новую запись
    new_vote = DaoVote(
        proposal_id=proposal_id,
        user_id=user_id,
        option_id=option_id,
        weight=int(weight),
        # created_at не выставляем руками — сработает server_default=now()
    )
    session.add(new_vote)
    return new_vote
