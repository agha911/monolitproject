from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.crud import crud_challenge
from app.crud.user import get_user  # чтобы получить user по telegram_id

router = APIRouter(prefix="/api/challenge", tags=["challenge"])


# ====== схемы запросов ======
class WatchRequest(BaseModel):
    telegram_id: int
    day_index: int = Field(ge=1, le=5)

class AnswerRequest(BaseModel):
    telegram_id: int
    day_index: int = Field(ge=1, le=5)
    selected_option: str  # 'A' | 'B' | 'C' | 'D'

class FinalSubmitRequest(BaseModel):
    telegram_id: int
    keywords: list[str]  # ровно 5 слов, порядок важен


# ====== endpoints ======

@router.get("/config")
async def get_config():
    """
    Вернуть публичную конфигурацию квеста:
    - enabled, final_reward, version
    - days (без correct_option и codeword)
    """
    return await crud_challenge.get_config()


@router.get("/progress")
async def get_progress(telegram_id: int, session: AsyncSession = Depends(get_async_session)):
    """
    Сводка прогресса пользователя + готов ли финал.
    Также включает:
      - allowed_day (максимально доступный по календарю Баку),
      - next_required_day (какой день должен проходить сейчас),
      - seconds_to_next_day (секунд до следующей полуночи Баку).
    """
    user = await get_user(session, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    data = await crud_challenge.get_progress_with_final_state(session, user.id)
    await session.commit()
    return data


@router.post("/watch")
async def mark_watched(body: WatchRequest, session: AsyncSession = Depends(get_async_session)):
    """
    Отметить просмотр для day_index, начислить разовую награду за просмотр.
    Если день ещё не открыт по календарю Баку, вернёт 409 DAY_LOCKED.
    """
    user = await get_user(session, body.telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        data = await crud_challenge.mark_watched(session, user.id, body.day_index)
        await session.commit()
        return data
    except ValueError as e:
        await session.rollback()
        msg = str(e)
        if msg.startswith("day_locked:"):
            try:
                n = int(msg.split(":", 1)[1])
            except Exception:
                n = None
            raise HTTPException(status_code=409, detail={"code": "DAY_LOCKED", "next_required_day": n})
        raise HTTPException(status_code=400, detail=msg)


@router.post("/answer")
async def submit_answer(body: AnswerRequest, session: AsyncSession = Depends(get_async_session)):
    """
    Принять ответ (A/B/C/D), выдать разовую награду за факт ответа.
    Если верно и кодовое слово ещё не показывали — вернуть codeword.
    Если день ещё не открыт по календарю Баку, вернёт 409 DAY_LOCKED.
    """
    user = await get_user(session, body.telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        data = await crud_challenge.submit_answer(
            session, user.id, body.day_index, body.selected_option
        )
        await session.commit()
        return data
    except ValueError as e:
        await session.rollback()
        msg = str(e)
        if msg.startswith("day_locked:"):
            try:
                n = int(msg.split(":", 1)[1])
            except Exception:
                n = None
            raise HTTPException(status_code=409, detail={"code": "DAY_LOCKED", "next_required_day": n})
        raise HTTPException(status_code=400, detail=msg)


@router.post("/final/submit")
async def final_submit(body: FinalSubmitRequest, session: AsyncSession = Depends(get_async_session)):
    """
    Принять 5 код-слов по порядку, при успехе выдать финальную награду (один раз).
    """
    user = await get_user(session, body.telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        data = await crud_challenge.submit_final(session, user.id, body.keywords)
        await session.commit()
        return data
    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))


