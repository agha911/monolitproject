from fastapi import APIRouter, Depends, Query, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_async_session
from app.crud import user as crud_user
from app.utils import parse_telegram_user_id

router = APIRouter(prefix="/api/tournament", tags=["Tournament"])

@router.get("/leaderboard")
async def tournament_leaderboard(
    league: str = Query(..., regex="^(bronze|silver|gold)$"),
    session: AsyncSession = Depends(get_async_session)
):
    try:
        users = await crud_user.get_tournament_leaderboard(session, league)
        return [
            {
                "username": user.username,
                "clicks": user.tournament_clicks,
                "rank": i + 1
            }
            for i, user in enumerate(users)
        ]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid league")


@router.get("/me")
async def tournament_me(
    request: Request,
    session: AsyncSession = Depends(get_async_session)
):
    user_id = parse_telegram_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    info = await crud_user.get_user_tournament_info(session, user_id)

    if info is None:
        raise HTTPException(status_code=404, detail="User not found")

    return info
