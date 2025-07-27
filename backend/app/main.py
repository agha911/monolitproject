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
from app.core.referral_cache import referral_cache
from app.bot_instance import bot
import threading
from app.config import TELEGRAM_BOT_TOKEN
import time
from telebot.apihelper import ApiTelegramException
from app.notifications.notify_energy import notify_max_energy_users
import asyncio
from telebot import types
from app.notifications.reset_energy_notified import reset_energy_flags
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import concurrent.futures

ENERGY_RECOVERY_TOTAL_MINUTES = 480
MAX_ENERGY = 100
DAILY_REWARDS = [100, 200, 300, 400, 500, 600, 700]

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

@bot.message_handler(commands=["start"])
async def handle_start(message: types.Message):
    user_telegram_id = str(message.from_user.id)
    parts = message.text.split()
    if len(parts) > 1 and parts[1].isdigit():
        inviter_telegram_id = str(int(parts[1]))
        referral_cache[user_telegram_id] = inviter_telegram_id
        print(f"[REF-CACHE] {user_telegram_id} invited by {inviter_telegram_id}")

    info = get_user_info_from_bot_api(int(user_telegram_id))
    print(f"[USER INFO] {info}")

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🚀 Başla", web_app=WebAppInfo(url="https://monolitproject-5g7v.vercel.app/")))

    await bot.send_message(
        chat_id=message.chat.id,
        text=(
            "👋 Salam! Gappick-ə xoş gəlmiəsən!\n\n"
            "Oyuna başlamaq üçün aşağıdakı düyməni kliklə."
        ),
        reply_markup=markup
    )

@app.post("/api/user/register")
async def register_user(
    data: dict = Body(...),
    session: AsyncSession = Depends(get_async_session),
):
    init_data = data.get("init_data")
    if not init_data:
        raise HTTPException(status_code=400, detail="init_data is required")

    telegram_id = int(parse_telegram_user_id(init_data))
    telegram_id_str = str(telegram_id)

    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()

    info = get_user_info_from_bot_api(telegram_id)

    inviter_id_str = referral_cache.get(telegram_id_str)
    inviter = None

    if user:
        if inviter_id_str and user.invited_by is None:
            inviter_id = int(inviter_id_str)
            inviter_result = await session.execute(select(User).where(User.telegram_id == inviter_id))
            inviter = inviter_result.scalar_one_or_none()
            if inviter:
                user.invited_by = inviter.id
                user.invited_at = datetime.utcnow() + timedelta(hours=4)
                inviter.invites_count += 1
                inviter.total_xp += 1500
                session.add_all([user, inviter])
                await session.commit()
        return {"status": "already_registered"}

    if inviter_id_str:
        inviter_id = int(inviter_id_str)
        inviter_result = await session.execute(select(User).where(User.telegram_id == inviter_id))
        inviter = inviter_result.scalar_one_or_none()
        if inviter:
            inviter.invites_count += 1
            inviter.total_xp += 1500
            session.add(inviter)

    new_user = User(
        telegram_id=telegram_id,
        invited_by=inviter.id if inviter else None,
        invited_at=datetime.utcnow() + timedelta(hours=4) if inviter else None,
        username=info.get("username"),
        first_name=info.get("first_name"),
        last_name=info.get("last_name"),
    )
    session.add(new_user)
    await session.commit()

    return {"status": "ok"}

@app.post("/api/game/progress")
async def get_progress(data: dict = Body(...), session: AsyncSession = Depends(get_async_session)):
    telegram_id = parse_telegram_user_id(data["init_data"])
    user = await crud_user.get_user(session, telegram_id)
    if not user:
        return {
            "energy": 100,
            "total_xp": 0,
            "max_energy": 100,
            "lastEnergyUpdate": None,
            "click_boost_level": 0,
        }

    now = datetime.utcnow()
    last_update = user.lastEnergyUpdate
    max_energy = user.max_energy or 100

    if last_update:
        minutes_passed = (now - last_update).total_seconds() / 60
        recovery_interval = ENERGY_RECOVERY_TOTAL_MINUTES / max_energy
        energy_to_restore = int(minutes_passed // recovery_interval)

        if energy_to_restore > 0 and user.energy < max_energy:
            new_energy = min(max_energy, user.energy + energy_to_restore)

            # ⏱️ Вычисляем, сколько времени прошло на восстановление этой энергии
            updated_minutes = recovery_interval * (new_energy - user.energy)

            # ⏳ Обновляем только на ту часть времени, которая реально "израсходована"
            new_last_update = last_update + timedelta(minutes=updated_minutes)
        else:
            new_energy = user.energy
            new_last_update = last_update

        await crud_user.update_energy_and_time(session, telegram_id, new_energy, new_last_update)
        user.energy = new_energy
        user.lastEnergyUpdate = new_last_update
    else:
        await crud_user.update_energy_and_time(session, telegram_id, user.energy, now)
        user.lastEnergyUpdate = now

    return {
        "energy": user.energy,
        "total_xp": user.total_xp,
        "max_energy": user.max_energy,
        "lastEnergyUpdate": user.lastEnergyUpdate.isoformat() if user.lastEnergyUpdate else None,
        "click_boost_level": user.click_boost_level or 0,
    }


@app.post("/api/game/save_progress")
async def save_progress(data: dict = Body(...), session: AsyncSession = Depends(get_async_session)):
    try:
        telegram_id = parse_telegram_user_id(data["init_data"])
        await crud_user.update_progress(
            session=session,
            telegram_id=telegram_id,
            energy=data["energy"],
            total_xp=data.get("total_xp", 0),
        )
        print(f"[SAVED] {telegram_id} → ENERGY: {data['energy']}")
        return {"status": "saved"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/game/click")
async def click(data: dict = Body(...), session: AsyncSession = Depends(get_async_session)):
    try:
        telegram_id = parse_telegram_user_id(data["init_data"])
        user = await crud_user.get_user(session, telegram_id)
        if user:
            click_value = (user.click_boost_level or 0) + 1
            await crud_user.update_progress(
                session=session,
                telegram_id=telegram_id,
                energy=user.energy,
                total_xp=user.total_xp + click_value
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

@app.post("/api/tournament/leaderboard")
async def get_tournament_leaderboard(
    data: dict = Body(...),
    session: AsyncSession = Depends(get_async_session),
):
    telegram_id = parse_telegram_user_id(data["init_data"])

    now_utc = datetime.utcnow()
    utc_offset = timedelta(hours=4)
    start_of_week = (now_utc + utc_offset).replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_week -= timedelta(days=start_of_week.weekday())
    start_utc = start_of_week - utc_offset
    end_of_week = start_of_week + timedelta(days=5, hours=23, minutes=59, seconds=59)
    end_utc = end_of_week - utc_offset

    stmt = (
        select(
            User.invited_by,
            func.count(User.id).label("weekly_invites")
        )
        .where(
            User.invited_at >= start_utc,
            User.invited_at <= end_utc,
            User.invited_by.isnot(None)
        )
        .group_by(User.invited_by)
        .order_by(func.count(User.id).desc())
    )

    results = await session.execute(stmt)
    rows = results.fetchall()

    leaderboard = []
    my_rank = None
    my_score = 0

    for idx, row in enumerate(rows):
        user_id = row.invited_by
        score = row.weekly_invites

        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        if not user:
            continue

        entry = {
            "rank": idx + 1,
            "telegram_id": user.telegram_id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "score": score,
        }

        leaderboard.append(entry)

        if user.telegram_id == telegram_id:
            my_rank = idx + 1
            my_score = score

    top_10 = leaderboard[:10]

    if my_rank is None:
        for idx, row in enumerate(rows):
            if row.invited_by == telegram_id:
                my_rank = idx + 1
                my_score = row.weekly_invites
                break

    return {
        "top_10": top_10,
        "my_rank": my_rank,
        "my_score": my_score,
    }

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

app.include_router(task.router)
app.include_router(shop.router)
app.include_router(invites.router)

async def reset_loop():
    while True:
        try:
            await reset_energy_flags()
        except Exception as e:
            print(f"[RESET ERROR] {e}")
        await asyncio.sleep(24 * 60 * 60)

async def run_bot_polling():
    print("[BOT] Starting polling...")
    await bot.infinity_polling()

@app.on_event("startup")
async def start_background_tasks():
    asyncio.create_task(notify_loop())
    asyncio.create_task(reset_loop())
    asyncio.create_task(run_bot_polling())

async def notify_loop():
    while True:
        now = datetime.utcnow() + timedelta(hours=4)
        if 10 <= now.hour < 22:
            try:
                await notify_max_energy_users()
            except Exception as e:
                print(f"[NOTIFY ERROR] {e}")
        await asyncio.sleep(3600)






