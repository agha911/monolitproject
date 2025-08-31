from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_session
from app.crud.crud_tournament_winner import finalize_tournament_winners

router = APIRouter(prefix="/api/tournament", tags=["tournament-admin"])

@router.post("/finalize")
async def api_finalize_tournament(
    period_start: datetime = Query(..., description="UTC start"),
    period_end: datetime   = Query(..., description="UTC end"),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        winners = await finalize_tournament_winners(session, period_start, period_end)
        return {
            "status": "ok",
            "count": len(winners),
            "winners": [
                {
                    "id": w.id,
                    "league": w.league,
                    "rank": w.rank_in_league,
                    "user_id": w.user_id,
                    "username": w.username_snapshot,
                    "clicks": w.clicks_snapshot,
                } for w in winners
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
