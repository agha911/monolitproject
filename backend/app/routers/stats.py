from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_async_session
from app.crud import user as crud_stats  # 🔄 исправлено

router = APIRouter(prefix="/api/stats", tags=["Stats"])


@router.get("/total-spent")
async def total_spent(session: AsyncSession = Depends(get_async_session)):
    amount = await crud_stats.get_total_spent(session)
    return {"total_spent": amount}

