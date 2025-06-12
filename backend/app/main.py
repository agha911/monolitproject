from fastapi import FastAPI, Depends, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, func
from datetime import datetime, timedelta
import requests
from typing import Optional
import os

from app.database import get_async_session
from app.crud import user as crud_user
from app.routers import task, shop, invites
from sqlalchemy.future import select
from app.models.user import User
from app.utils import parse_telegram_user_id

ENERGY_RECOVERY_INTERVAL_MINUTES = 1
MAX_ENERGY = 100
DAILY_REWARDS = [10, 15, 20, 25, 30, 40, 50]
TELEGRAM_BOT_TOKEN = "7804408659:AAEzVuke_9BSluke6J5tmDInjn5jbh3B5tE"

app = FastAPI()
print("[APP] Using DATABASE_URL:", os.getenv("DATABASE_URL"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_user_info_from_bot_api(user_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getChat"
    params = {"chat_id": user_id}
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if data.get("ok"):
            result = data["result"]
            return {
                "first_name": result.get("first_name", ""),
                "last_name": result.get("last_name", ""),
                "username": result.get("username", ""),
            }
    except Exception as e:
        print(f"[GETCHAT ERROR] {e}")
    return {}

@app.post("/api/user/register")
async def register_user(
    data: dict = Body(...),
    inviter_id: Optional[int] = None,
    session: AsyncSession = Depends(get_async_session),
):
    init_data = data.get("init_data")
    if not init_data:
        raise HTTPException(status_code=400, detail="init_data is required")

    telegram_id = parse_telegram_user_id(init_data)

    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()

    if user:
        # 🔁 Пользователь уже есть: проверяем, можно ли применить рефералку
        if inviter_id and user.invited_by is None:
            inviter_result = await session.execute(select(User).where(User.id == inviter_id))
            inviter = inviter_result.scalar_one_or_none()
            if inviter:
                user.invited_by = inviter.id
                inviter.invites_count = (inviter.invites_count or 0) + 1
                inviter.total_xp = (inviter.total_xp or 0) + 200
                session.add_all([user, inviter])
                await session.commit()
                return {"status": "referral_applied"}
        return {"status": "already_registered"}

    # 🆕 Регистрация нового пользователя
    inviter = None
    if inviter_id:
        inviter_result = await session.execute(select(User).where(User.id == inviter_id))
        inviter = inviter_result.scalar_one_or_none()

    info = get_user_info_from_bot_api(telegram_id)

    new_user = User(
        telegram_id=telegram_id,
        invited_by=inviter.id if inviter else None,  # явно задаём None
        username=info.get("username"),
        first_name=info.get("first_name"),
        last_name=info.get("last_name"),
    )

    if inviter:
        inviter.invites_count = (inviter.invites_count or 0) + 1
        inviter.total_xp = (inviter.total_xp or 0) + 200
        session.add(inviter)

    session.add(new_user)
    await session.commit()
    return {"status": "ok"}




@app.post("/api/game/progress")
async def get_progress(data: dict = Body(...), session: AsyncSession = Depends(get_async_session)):
    telegram_id = parse_telegram_user_id(data["init_data"])
    user = await crud_user.get_user(session, telegram_id)
    if not user:
        return {
            "xp": 0, "level": 1, "energy": 100, "total_xp": 0,
            "max_energy": 100, "lastEnergyUpdate": None,
        }

    now = datetime.utcnow()
    last_update = user.lastEnergyUpdate
    max_energy = user.max_energy or 100

    if last_update:
        minutes_passed = int((now - last_update).total_seconds() // 60)
        energy_to_restore = minutes_passed // ENERGY_RECOVERY_INTERVAL_MINUTES

        if energy_to_restore > 0 and user.energy < max_energy:
            new_energy = min(max_energy, user.energy + energy_to_restore)
            await crud_user.update_energy_and_time(session, telegram_id, new_energy, now)
            user.energy = new_energy
            user.lastEnergyUpdate = now
    else:
        await crud_user.update_energy_and_time(session, telegram_id, user.energy, now)

    return {
        "xp": user.xp,
        "level": user.level,
        "energy": user.energy,
        "total_xp": user.total_xp,
        "max_energy": user.max_energy,
        "lastEnergyUpdate": user.lastEnergyUpdate.isoformat() if user.lastEnergyUpdate else None,
    }

@app.post("/api/game/save_progress")
async def save_progress(data: dict = Body(...), session: AsyncSession = Depends(get_async_session)):
    try:
        telegram_id = parse_telegram_user_id(data["init_data"])
        await crud_user.update_progress(
            session=session,
            telegram_id=telegram_id,
            xp=data["xp"],
            level=data["level"],
            energy=data["energy"],
            total_xp=data.get("total_xp", 0),
        )
        print(f"[SAVED] {telegram_id} → XP: {data['xp']}, LVL: {data['level']}, ENERGY: {data['energy']}")
        return {"status": "saved"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/game/click")
async def click(data: dict = Body(...), session: AsyncSession = Depends(get_async_session)):
    try:
        telegram_id = parse_telegram_user_id(data["init_data"])
        user = await crud_user.get_user(session, telegram_id)
        if user:
            await crud_user.update_progress(
                session=session,
                telegram_id=telegram_id,
                xp=user.xp,
                level=user.level,
                energy=user.energy,
                total_xp=user.total_xp + 1
            )
        return {"status": "clicked"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/game/leaderboard")
async def leaderboard(session: AsyncSession = Depends(get_async_session)):
    users = await crud_user.get_leaderboard(session)
    return [
        {
            "id": u.id,
            "username": u.username or u.first_name or f"user_{u.id}",
            "total_xp": u.total_xp
        } for u in users
    ]

@app.get("/")
def root():
    return {"status": "ok", "message": "Backend is live!"}

@app.get("/ping-db")
async def ping_db(session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(text("SELECT 1"))
    return {"status": "ok", "result": result.scalar()}

@app.get("/api/user/count")
async def count_users(session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(select(func.count(User.id)))
    count = result.scalar()
    return {"count": count}

app.include_router(task.router, prefix="/api/task")
app.include_router(shop.router, prefix="/api/shop")
app.include_router(invites.router)



