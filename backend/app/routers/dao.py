# app/routers/dao.py

from __future__ import annotations

from datetime import datetime
from typing import List, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_async_session
from app.utils import parse_telegram_user_id
from app.crud import user as crud_user
from app.crud import dao as crud_dao
from app.models.dao import DaoProposal, DaoOption, ArtWork
from app.models.user import User
import logging

log = logging.getLogger("dao.vote")

router = APIRouter(prefix="/api/dao", tags=["dao"])


# ─────────────────────────
# Pydantic-схемы
# ─────────────────────────

class VoteItem(BaseModel):
    option_id: int = Field(..., ge=1)
    weight: int = Field(..., ge=1)


class VoteRequest(BaseModel):
    init_data: str
    votes: List[VoteItem]


class VoteResponse(BaseModel):
    status: str
    used_weight: int
    balance: int


class DaoOptionArtOut(BaseModel):
    id: int
    label: str | None
    art_work_id: int | None
    art_title: str | None
    art_image_url: str | None
    art_author_telegram_id: int | None


class DaoProposalOut(BaseModel):
    id: int
    title: str
    description: str
    starts_at: datetime
    ends_at: datetime
    options: List[DaoOptionArtOut]


class DaoResultItem(BaseModel):
    option_id: int
    art_work_id: int | None
    label: str | None
    art_title: str | None
    art_image_url: str | None
    total_weight: int
    votes_count: int


class DaoResultsOut(BaseModel):
    proposal_id: int
    title: str
    results: List[DaoResultItem]


# ─────────────────────────
# helpers
# ─────────────────────────

async def _load_proposal_or_404(
    session: AsyncSession,
    proposal_id: int,
) -> DaoProposal:
    proposal = await crud_dao.get_proposal(session, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="proposal_not_found")
    return proposal


async def _load_options_with_art(
    session: AsyncSession,
    proposal_id: int,
) -> list[DaoOptionArtOut]:
    options = await crud_dao.list_options_for_proposal(session, proposal_id)

    # Загружаем все ArtWork одним запросом, чтобы не делать N+1
    art_ids = {opt.art_work_id for opt in options if opt.art_work_id is not None}
    art_map: Dict[int, ArtWork] = {}

    if art_ids:
        res = await session.execute(
            select(ArtWork).where(ArtWork.id.in_(art_ids))
        )
        for art in res.scalars().all():
            art_map[art.id] = art

    out: list[DaoOptionArtOut] = []
    for opt in options:
        art = art_map.get(opt.art_work_id) if opt.art_work_id else None
        out.append(
            DaoOptionArtOut(
                id=opt.id,
                label=opt.label,
                art_work_id=opt.art_work_id,
                art_title=art.title if art else None,
                art_image_url=art.image_url if art else None,
                art_author_telegram_id=art.author_telegram_id if art else None,
            )
        )
    return out


# ─────────────────────────
# GET /api/dao/proposals/active
# ─────────────────────────

@router.get("/proposals/active", response_model=list[DaoProposalOut])
async def list_active_proposals(
    session: AsyncSession = Depends(get_async_session),
):
    """
    Список активных голосований (is_active = true, текущее время в окне).
    Для каждого — варианты + привязанные арт-работы (картинка, название, автор).
    """
    now = datetime.utcnow()
    proposals = await crud_dao.list_active_proposals(session, now_utc=now)

    result: list[DaoProposalOut] = []
    for p in proposals:
        options_out = await _load_options_with_art(session, p.id)
        result.append(
            DaoProposalOut(
                id=p.id,
                title=p.title,
                description=p.description,
                starts_at=p.starts_at,
                ends_at=p.ends_at,
                options=options_out,
            )
        )
    return result


# ─────────────────────────
# POST /api/dao/proposals/{id}/vote
# ─────────────────────────

@router.post("/proposals/{proposal_id}/vote", response_model=VoteResponse)
async def vote_for_proposal(
    proposal_id: int,
    payload: VoteRequest,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Принять голоса пользователя по одному голосованию.

    Логика:
    - init_data → telegram_id → User
    - проверяем, что proposal активен
    - проверяем, что option_id принадлежат proposal
    - вызываем cast_vote для каждой опции
    - commit / rollback без session.begin(), чтобы не ловить
      `A transaction is already begun on this Session`
    """
    # --- находим пользователя по init_data ---
    try:
        telegram_id = int(parse_telegram_user_id(payload.init_data))
    except Exception:
        raise HTTPException(status_code=400, detail="bad_init_data")

    user: User | None = await crud_user.get_user(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="user_not_found")

    user_id = int(user.id)  # сохраняем простое значение, чтобы не трогать ORM в except

    if not payload.votes:
        raise HTTPException(status_code=400, detail="empty_votes")

    # --- загружаем предложение ---
    proposal = await _load_proposal_or_404(session, proposal_id)
    proposal_id_int = int(proposal.id)

    # --- загружаем опции и мапим по id ---
    options = await crud_dao.list_options_for_proposal(session, proposal_id_int)
    options_map: Dict[int, DaoOption] = {o.id: o for o in options}

    # проверяем, что все option_id принадлежат этому proposal
    for v in payload.votes:
        if v.option_id not in options_map:
            raise HTTPException(
                status_code=400,
                detail=f"option_not_in_proposal:{v.option_id}",
            )

    from sqlalchemy import exc as sa_exc

    # --- основная часть без session.begin() ---
    try:
        # блокируем пользователя (как в clicker)
        db_user = await crud_user.get_user_for_update(session, user_id)
        if not db_user:
            raise HTTPException(status_code=404, detail="user_not_found")

        # применяем все голоса
        for v in payload.votes:
            opt = options_map[v.option_id]
            await crud_dao.cast_vote(
                session=session,
                proposal=proposal,
                option=opt,
                user=db_user,
                weight=v.weight,
            )

        # фиксируем изменения
        await session.commit()

    except HTTPException:
        # если где-то внутри мы кинули HTTPException — просто откатываем и пробрасываем
        await session.rollback()
        raise

    except ValueError as e:
        # ValueError — это наши бизнес-ошибки из cast_vote (например insufficient_balance)
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    except sa_exc.SQLAlchemyError:
        # всё остальное — настоящие DB-ошибки
        await session.rollback()
        log.exception(
            "dao.vote.db_error | proposal_id=%s user_id=%s votes=%s",
            proposal_id_int,
            user_id,
            [(v.option_id, v.weight) for v in payload.votes],
        )
        raise HTTPException(status_code=500, detail="db_error_internal")

    # --- если мы здесь — всё успешно закоммичено ---
    used_weight = await crud_dao.get_user_vote_total_weight(
        session,
        proposal_id=proposal_id_int,
        user_id=user_id,
    )

    # показываем актуальный баланс (на голосование мы его не уменьшаем)
    balance = int(user.total_xp or 0)

    return VoteResponse(
        status="ok",
        used_weight=used_weight,
        balance=balance,
    )


# ─────────────────────────
# GET /api/dao/proposals/{id}/results
# ─────────────────────────

@router.get("/proposals/{proposal_id}/results", response_model=DaoResultsOut)
async def get_proposal_results(
    proposal_id: int,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Агрегированные результаты голосования:
    - суммарный weight по каждому варианту;
    - количество отдельных голосов (сколько раз голосовали за вариант).
    + Дёргаем ArtWork, чтобы фронт мог сразу показать картинку и заголовок.
    """
    proposal = await _load_proposal_or_404(session, proposal_id)

    raw_results = await crud_dao.get_proposal_results(session, proposal_id)

    # Собираем все art_work_id, чтобы достать одним запросом
    art_ids = {r["art_work_id"] for r in raw_results if r["art_work_id"] is not None}
    art_map: Dict[int, ArtWork] = {}

    if art_ids:
        res = await session.execute(
            select(ArtWork).where(ArtWork.id.in_(art_ids))
        )
        for art in res.scalars().all():
            art_map[art.id] = art

    items: list[DaoResultItem] = []
    for r in raw_results:
        art = art_map.get(r["art_work_id"]) if r["art_work_id"] else None
        items.append(
            DaoResultItem(
                option_id=r["option_id"],
                art_work_id=r["art_work_id"],
                label=r["label"],
                art_title=art.title if art else None,
                art_image_url=art.image_url if art else None,
                total_weight=int(r["total_weight"] or 0),
                votes_count=int(r["votes_count"] or 0),
            )
        )

    return DaoResultsOut(
        proposal_id=proposal.id,
        title=proposal.title,
        results=items,
    )
