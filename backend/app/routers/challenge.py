from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_async_session, get_current_user
from app.crud import crud_challenge

router = APIRouter(prefix="/api/challenge", tags=["challenge"])


# --- схемы запросов/ответов ---
class AnswerRequest(BaseModel):
    day_index: int = Field(ge=1, le=5)
    selected_option: str  # 'A'|'B'|'C'|'D'


class FinalSubmitRequest(BaseModel):
    keywords: list[str]  # длина 5, порядок важен


# --- endpoints ---
@router.get("/config")
async def get_config():
    """Вернуть конфигурацию (enabled, final_reward, days без правильных ответов)."""
    return await crud_challenge.get_config()


@router.get("/progress")
async def get_progress(
    session: AsyncSession = Depends(get_async_session),
    user=Depends(get_current_user),
):
    data = await crud_challenge.get_progress_with_final_state(session, user.id)
    await session.commit()
    return data


@router.post("/watch/{day_index}")
async def mark_watched(
    day_index: int,
    session: AsyncSession = Depends(get_async_session),
    user=Depends(get_current_user),
):
    try:
        data = await crud_challenge.mark_watched(session, user.id, day_index)
        await session.commit()
        return data
    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/answer")
async def submit_answer(
    body: AnswerRequest,
    session: AsyncSession = Depends(get_async_session),
    user=Depends(get_current_user),
):
    try:
        data = await crud_challenge.submit_answer(
            session, user.id, body.day_index, body.selected_option
        )
        await session.commit()
        return data
    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/final/submit")
async def final_submit(
    body: FinalSubmitRequest,
    session: AsyncSession = Depends(get_async_session),
    user=Depends(get_current_user),
):
    try:
        data = await crud_challenge.submit_final(session, user.id, body.keywords)
        await session.commit()
        return data
    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
