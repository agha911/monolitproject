# app/routers/partner_task.py
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime
from typing import Dict, Any, Optional

from app.database import get_async_session
from app.models.user import User
from app.utils import parse_telegram_user_id

router = APIRouter(prefix="/api/partner", tags=["partner"])

# === ТЕКУЩЕЕ АКТИВНОЕ ЗАДАНИЕ (можно редактировать без деплоя БД) ===
# Если понадобится несколько задач — вынесем в таблицу partners и user_partner_tasks.
PARTNER_TASK = {
    "id": "promo_express_2025_08",               # <= важен для единовременной выдачи
    "partner_name": "Promo Express",
    "ig_username": "promoexpress_azerbaijan",
    "ig_url": "https://instagram.com/promoexpress_azerbaijan",
    "reward": 500_000,
    # Короткая презентация — 2–3 слайда. Можно добавить/убрать изображения.
    "slides": [
        {
            "title": "Promo Express nədir?",
            "text": "Promo Express — Azərbaycanın aparıcı promo məhsul istehsalçısıdır.",
            "image": "https://your-cdn.example/partners/promoexpress/slide1.png",
        },
        {
            "title": "Onlar nə edirlər?",
            "text": "Brand geyim, suvenir və POS materialları hazırlayırlar.",
            "image": "https://your-cdn.example/partners/promoexpress/slide2.png",
        },
        {
            "title": "Niyə vacibdir?",
            "text": "Promo məhsullar tədbirlər, reklam və hədiyyələr üçün idealdır.",
            "image": "https://your-cdn.example/partners/promoexpress/slide3.png",
        },
    ],
}

def _safe_parse_tid(init_data: Optional[str]) -> Optional[int]:
    if not init_data:
        return None
    try:
        return parse_telegram_user_id(init_data)
    except Exception:
        return None

@router.post("/task")
async def get_partner_task(
    data: Dict[str, Any] = Body(...),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Возвращает активное партнёрское задание.
    Если пользователь авторизован (init_data), добавляет флаг claimed.
    """
    init_data = data.get("init_data") or data.get("initData")
    telegram_id = _safe_parse_tid(init_data)

    claimed = False
    if telegram_id is not None:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if user and getattr(user, "partner_task_claimed_id", None) == PARTNER_TASK["id"]:
            claimed = True

    # Отдаём всё, что нужно фронту для модалки со слайдами
    return {
        "id": PARTNER_TASK["id"],
        "partner_name": PARTNER_TASK["partner_name"],
        "slides": PARTNER_TASK["slides"],
        "ig_username": PARTNER_TASK["ig_username"],
        "ig_url": PARTNER_TASK["ig_url"],
        "reward": PARTNER_TASK["reward"],
        "claimed": claimed,
    }

@router.post("/claim")
async def claim_partner_reward(
    data: Dict[str, Any] = Body(...),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Начисляет награду за партнёрское задание один раз на пользователя.
    Вызывать сразу после клика по кнопке «Подписаться».
    """
    telegram_id = _safe_parse_tid(data.get("init_data") or data.get("initData"))
    if telegram_id is None:
        raise HTTPException(status_code=400, detail="init_data missing or invalid")

    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if getattr(user, "partner_task_claimed_id", None) == PARTNER_TASK["id"]:
        return {"status": "already_claimed"}

    # начисляем
    before = int(user.total_xp or 0)
    user.total_xp = before + int(PARTNER_TASK["reward"])
    user.partner_task_claimed_id = PARTNER_TASK["id"]

    session.add(user)
    await session.commit()

    return {
        "status": "ok",
        "reward": int(PARTNER_TASK["reward"]),
        "total_xp_after": int(user.total_xp or 0),
    }
