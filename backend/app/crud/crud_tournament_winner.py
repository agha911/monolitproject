from __future__ import annotations
from typing import Iterable, List, Literal
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.models.db_tournament_winner import TournamentWinner
from app.models.db_user import User
from app.crud.crud_user import get_tournament_leaderboard  # твоя функция

League = Literal["bronze", "silver", "gold"]


async def finalize_tournament_winners(
    session: AsyncSession,
    period_start: datetime,
    period_end: datetime,
) -> List[TournamentWinner]:
    """
    Фиксирует ТОП-3 победителей в каждой лиге за указанный период.
    Делает UPSERT по уникальному ключу (period_start, period_end, league, rank_in_league).
    Возвращает ORM-объекты TournamentWinner для этого периода.
    """
    leagues: Iterable[League] = ("bronze", "silver", "gold")

    for league in leagues:
        users: List[User] = await get_tournament_leaderboard(session, league)
        top3 = users[:3]

        for rank, u in enumerate(top3, start=1):
            stmt = (
                insert(TournamentWinner)
                .values(
                    period_start=period_start,
                    period_end=period_end,
                    user_id=u.id,
                    username_snapshot=u.username,
                    league=league,
                    rank_in_league=rank,
                    clicks_snapshot=u.tournament_clicks,
                )
                .on_conflict_do_update(
                    index_elements=[
                        TournamentWinner.__table__.c.period_start,
                        TournamentWinner.__table__.c.period_end,
                        TournamentWinner.__table__.c.league,
                        TournamentWinner.__table__.c.rank_in_league,
                    ],
                    set_={
                        "user_id": u.id,
                        "username_snapshot": u.username,
                        "clicks_snapshot": u.tournament_clicks,
                        "updated_at": datetime.utcnow(),
                    },
                )
            )
            await session.execute(stmt)

    await session.commit()

    # Вернём все зафиксированные записи ТОП-3 (всех лиг) за период
    q = await session.execute(
        select(TournamentWinner)
        .where(
            TournamentWinner.period_start == period_start,
            TournamentWinner.period_end == period_end,
            TournamentWinner.rank_in_league <= 3,
        )
        .order_by(
            TournamentWinner.league.asc(),
            TournamentWinner.rank_in_league.asc(),
        )
    )
    return q.scalars().all()


async def get_winners_for_period(
    session: AsyncSession,
    period_start: datetime,
    period_end: datetime,
) -> List[TournamentWinner]:
    """
    Возвращает (если уже финализировано) список победителей ТОП-3 по всем лигам за период.
    """
    q = await session.execute(
        select(TournamentWinner)
        .where(
            TournamentWinner.period_start == period_start,
            TournamentWinner.period_end == period_end,
            TournamentWinner.rank_in_league <= 3,
        )
        .order_by(
            TournamentWinner.league.asc(),
            TournamentWinner.rank_in_league.asc(),
        )
    )
    return q.scalars().all()

