from fastapi import FastAPI, Depends, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, func
from datetime import datetime, timedelta, timezone
import requests
from pydantic import BaseModel, Field
import os, sys, time, logging
import asyncio
from telebot import types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

from app.database import get_async_session, async_session_maker  # ← добавили async_session_maker
from app.crud import user as crud_user
from app.routers import task, shop, invites, tournament, stats, partner_task, challenge
from sqlalchemy.future import select
from app.models.user import User
from app.utils import parse_telegram_user_id
from app.core.referral_cache import referral_cache
from app.bot_instance import bot
from app.config import TELEGRAM_BOT_TOKEN
from app.notifications.notify_energy import notify_max_energy_users
from app.notifications.reset_energy_notified import reset_energy_flags  # не используем
from app.routers.tournament_admin import router as tournament_admin_router

# ---------------- logging setup ----------------

def setup_app_logging(level: str = None):
    level = (level or os.getenv("APP_LOG_LEVEL") or "INFO").upper()
    lvl = getattr(logging, level, logging.INFO)

    class UTCFormatter(logging.Formatter):
        converter = time.gmtime  # UTC timestamps

    fmt = "%(asctime)s %(levelname)s %(name)s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(lvl)
    handler.setFormatter(UTCFormatter(fmt=fmt, datefmt=datefmt))

    # root — сдержанно
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.WARNING)
    root.addHandler(handler)

    # наш namespace — говорливее
    app_logger = logging.getLogger("app")
    app_logger.setLevel(lvl)
    app_logger.propagate = False
    app_logger.handlers.clear()
    app_logger.addHandler(handler)  # свой хендлер

    # дочерние — поднимаются к "app"
    for name in ("app.api", "app.clicks", "app.energy", "app.tournament",
                 "app.daily", "app.users", "app.stats"):
        lg = logging.getLogger(name)
        lg.setLevel(lvl)
        lg.propagate = True
        lg.handlers.clear()

    # приглушим SQLAlchemy шум
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)

# применяем сразу при импорте
setup_app_logging()
api_log = logging.getLogger("app.api")

# ---------------- constants ----------------

ENERGY_RECOVERY_TOTAL_MINUTES = 480
ENERGY_REFILL_DAILY_LIMIT = 2
MAX_ENERGY = 1000
DAILY_REWARDS = [10000, 20000, 30000, 40000, 50000, 60000, 70000]
MAX_DELTA_PER_FLUSH = 50

# ---------------- app + CORS ----------------

app = FastAPI()
api_log.info("APP start | DATABASE_URL=%s", os.getenv("DATABASE_URL"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- helpers ----------------

def get_user_info_from_bot_api(user_id: int) -> dict:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getChat"
    params = {"chat_id": user_id}
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if data.get("ok"):
            r = data["result"]
            return {
                "first_name": r.get("first_name", ""),
                "last_name": r.get("last_name", ""),
                "username": r.get("username", ""),
            }
    except Exception as e:
        api_log.warning("GETCHAT error | user_id=%s err=%s", user_id, e)
    return {}

# ---------------- bot handlers ----------------

@bot.message_handler(commands=["start"])
async def handle_start(message: types.Message):
    user_telegram_id = str(message.from_user.id)
    parts = (message.text or "").split()
    if len(parts) > 1 and parts[1].isdigit():
        inviter_telegram_id = str(int(parts[1]))
        referral_cache[user_telegram_id] = inviter_telegram_id
        api_log.info("REF-CACHE set | user=%s invited_by=%s", user_telegram_id, inviter_telegram_id)

    info = get_user_info_from_bot_api(int(user_telegram_id))
    api_log.info("USER INFO | %s", info)

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🚀 Başla", web_app=WebAppInfo(url="https://monolitproject-5g7v.vercel.app/")))

    await bot.send_message(
        chat_id=message.chat.id,
        text=("👋 Salam! Gappick-ə xoş gəlmisən!\n\n"
              "Oyuna başlamaq üçün aşağıdakı düyməni kliklə."),
        reply_markup=markup
    )

# ---------------- API models ----------------

class ClicksFlushIn(BaseModel):
    init_data: str
    delta_clicks: int = Field(ge=1, le=MAX_DELTA_PER_FLUSH)
    client_seq: int = Field(ge=1)
    session_id: str

class ClicksFlushOut(BaseModel):
    status: str
    accepted_clicks: int
    energy: int
    total_xp: int
    daily_progress: int
    server_seq: int
    task_completed: bool

# ---------------- routes ----------------

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
        updated = False
        if not user.username and info.get("username"):
            user.username = info["username"]; updated = True
        if not user.first_name and info.get("first_name"):
            user.first_name = info["first_name"]; updated = True
        if not user.last_name and info.get("last_name"):
            user.last_name = info["last_name"]; updated = True
        if updated:
            session.add(user)
            await session.commit()

        if inviter_id_str and user.invited_by is None:
            inviter_id = int(inviter_id_str)
            inviter_result = await session.execute(select(User).where(User.telegram_id == inviter_id))
            inviter = inviter_result.scalar_one_or_none()
            if inviter:
                user.invited_by = inviter.id
                user.invited_at = datetime.utcnow() + timedelta(hours=4)
                inviter.invites_count += 1
                inviter.total_xp += 50000
                session.add_all([user, inviter])
                await session.commit()

        return {"status": "already_registered"}

    if inviter_id_str:
        inviter_id = int(inviter_id_str)
        inviter_result = await session.execute(select(User).where(User.telegram_id == inviter_id))
        inviter = inviter_result.scalar_one_or_none()
        if inviter:
            inviter.invites_count += 1
            inviter.total_xp += 50000
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
            "energy_refill_count": 0,
            "energy_refills_left": ENERGY_REFILL_DAILY_LIMIT,
            "daily_reward_claimed": False,
            "last_client_seq": 0,
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
            updated_minutes = recovery_interval * (new_energy - user.energy)
            new_last_update = now if new_energy == max_energy else last_update + timedelta(minutes=updated_minutes)
        else:
            new_energy = user.energy
            new_last_update = last_update
    else:
        new_energy = user.energy
        new_last_update = now

    await crud_user.update_energy_and_time(session, telegram_id, new_energy, new_last_update)

    if user.last_energy_refill and user.last_energy_refill.date() != now.date():
        user.energy_refill_count = 0
        session.add(user)
        await session.commit()

    energy_refills_left = max(0, ENERGY_REFILL_DAILY_LIMIT - (user.energy_refill_count or 0))

    # читаем заново авторитетные значения
    user = await crud_user.get_user(session, telegram_id)

    return {
        "energy": user.energy,
        "total_xp": user.total_xp,
        "max_energy": user.max_energy,
        "lastEnergyUpdate": user.lastEnergyUpdate.isoformat() if user.lastEnergyUpdate else None,
        "click_boost_level": user.click_boost_level or 0,
        "energy_refill_count": user.energy_refill_count or 0,
        "energy_refills_left": energy_refills_left,
        "daily_reward_claimed": user.daily_reward_claimed or False,
        "last_client_seq": user.last_client_seq or 0,
    }

@app.post("/api/game/clicks/flush", response_model=ClicksFlushOut)
async def clicks_flush(
    payload: ClicksFlushIn = Body(...),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        telegram_id = parse_telegram_user_id(payload.init_data)
        now_utc = datetime.now(timezone.utc)

        # входной лог запроса
        api_log.info(
            "FLUSH req | tg=%s session=%s delta=%s seq=%s",
            telegram_id, payload.session_id, payload.delta_clicks, payload.client_seq
        )

        async with session.begin():
            user = await crud_user.get_user(session, telegram_id)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            db_user = await crud_user.get_user_for_update(session, user.id)

            result = await crud_user.apply_clicks_flush(
                session=session,
                user=db_user,
                delta_clicks=payload.delta_clicks,
                client_seq=payload.client_seq,
                now_utc=now_utc,
            )

            # ежедневка (добиваем до completed если надо)
            if not (db_user.daily_completed or False):
                if (db_user.daily_progress or 0) >= (db_user.daily_target or 0) > 0:
                    db_user.daily_progress = db_user.daily_target
                    db_user.daily_completed = True

            # ВАЖНО: турнир инкремент уже делает CRUD внутри apply_clicks_flush.
            # Здесь повторно НЕ инкрементим, чтобы не удваивать.
            await session.flush()

            user_id = db_user.id
            task_completed = bool(db_user.daily_completed)
            energy = db_user.energy or 0
            total_xp = db_user.total_xp or 0
            daily_progress = db_user.daily_progress or 0
            server_seq = int(result["server_seq"])
            accepted_clicks = int(result["accepted_clicks"])

        status = "ok" if accepted_clicks > 0 else "noop"
        api_log.info(
            "FLUSH %s | user_id=%s tg=%s delta=%s accepted=%s seq=%s energy=%s xp=%s",
            status, user_id, telegram_id, payload.delta_clicks, accepted_clicks, server_seq, energy, total_xp
        )

        return ClicksFlushOut(
            status=status,
            accepted_clicks=accepted_clicks,
            energy=energy,
            total_xp=total_xp,
            daily_progress=daily_progress,
            server_seq=server_seq,
            task_completed=task_completed,
        )

    except HTTPException:
        raise
    except Exception as e:
        api_log.exception("FLUSH error")
        return ClicksFlushOut(
            status=f"error: {str(e)}",
            accepted_clicks=0,
            energy=0,
            total_xp=0,
            daily_progress=0,
            server_seq=0,
            task_completed=False,
        )

@app.post("/api/daily/claim_reward")
async def claim_daily_reward(data: dict = Body(...), session: AsyncSession = Depends(get_async_session)):
    try:
        telegram_id = parse_telegram_user_id(data["init_data"])
        user = await crud_user.get_user(session, telegram_id)

        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if not user.daily_completed:
            return {"status": "not_completed"}
        if user.daily_reward_claimed:
            return {"status": "already_claimed"}

        reward = 50000
        user.total_xp = (user.total_xp or 0) + reward
        user.daily_reward_claimed = True

        session.add(user)
        await session.commit()
        await session.refresh(user)

        return {"status": "reward_claimed", "reward": reward, "total_xp": user.total_xp}

    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/game/leaderboard")
async def leaderboard(session: AsyncSession = Depends(get_async_session)):
    users = await crud_user.get_leaderboard(session)
    return [
        {"id": u.id, "username": u.username or u.first_name or f"user_{u.id}", "total_xp": u.total_xp}
        for u in users
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
        select(User.invited_by, func.count(User.id).label("weekly_invites"))
        .where(User.invited_at >= start_utc, User.invited_at <= end_utc, User.invited_by.isnot(None))
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
        u = user_result.scalar_one_or_none()
        if not u:
            continue

        leaderboard.append({
            "rank": idx + 1,
            "telegram_id": u.telegram_id,
            "username": u.username,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "score": score,
        })

        if u.telegram_id == telegram_id:
            my_rank = idx + 1
            my_score = score

    top_10 = leaderboard[:10]

    if my_rank is None:
        for idx, row in enumerate(rows):
            if row.invited_by == telegram_id:
                my_rank = idx + 1
                my_score = row.weekly_invites
                break

    return {"top_10": top_10, "my_rank": my_rank, "my_score": my_score}

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
app.include_router(tournament.router)
app.include_router(stats.router)
app.include_router(partner_task.router)
app.include_router(challenge.router)
app.include_router(tournament_admin_router)

# ---------------- background ----------------

async def run_bot_polling():
    api_log.info("[BOT] Starting polling…")
    await bot.infinity_polling()

# --- еженедельный сброс турнира (воскресенье по AZ, UTC+4) ---
_last_tournament_reset_az = None  # хранит az-date последнего сброса

async def tournament_reset_loop():
    """
    Ресеты турнира только два раза:
    - старт турнира:   2025-08-18 00:00:00 (UTC+4, Баку)
    - конец турнира:   2025-09-01 23:59:59 (UTC+4, Баку)
    После финального ресета цикл останавливается.
    """
    global _last_tournament_reset_az

    # Локальные (AZ, UTC+4) границы турнира
    START_AZ = datetime(2025, 8, 18, 0, 0, 0)       # 18 авг 00:00
    END_AZ   = datetime(2025, 9, 1, 23, 59, 59)     # 1 сен 23:59:59
    AZ_OFFSET = timedelta(hours=4)

    # Утилита: получить «сейчас» в AZ (наивный datetime, как и раньше)
    def now_az():
        return datetime.utcnow() + AZ_OFFSET

    # Хелпер для безопасного вызова ресета
    async def _do_reset(tag: str):
        global _last_tournament_reset_az
        az_now = now_az()
        api_log.warning("[TOURNAMENT] Reset (%s): start | az_now=%s", tag, az_now.isoformat())
        async with async_session_maker() as session:
            await crud_user.reset_tournament_data(session)
        _last_tournament_reset_az = az_now.date()
        api_log.warning("[TOURNAMENT] Reset (%s): done  | az_now=%s", tag, az_now.isoformat())

    while True:
        try:
            az_now = now_az()

            # --- Ресет в начале турнира ---
            if az_now >= START_AZ and az_now <= END_AZ:
                if _last_tournament_reset_az != START_AZ.date():
                    await _do_reset("tournament_start")

            # --- Ресет в конце турнира ---
            if az_now >= END_AZ and _last_tournament_reset_az != END_AZ.date():
                await _do_reset("tournament_end")

            # Если турнир завершён и финальный ресет уже выполнен — выходим из цикла
            if az_now.date() > END_AZ.date() and _last_tournament_reset_az == END_AZ.date():
                api_log.warning("[TOURNAMENT] Period finished. Loop is shutting down.")
                return

        except Exception as e:
            api_log.exception("[TOURNAMENT] Fixed-period reset error: %s", e)

        # Проверяем раз в 10 минут (как и раньше)
        await asyncio.sleep(600)


async def reset_loop():
    while True:
        try:
            await reset_energy_flags()
        except Exception as e:
            print(f"[RESET ERROR] {e}")
        await asyncio.sleep(24 * 60 * 60)


@app.on_event("startup")
async def start_background_tasks():
    asyncio.create_task(notify_loop())
    #asyncio.create_task(reset_loop())
    asyncio.create_task(run_bot_polling())
    #asyncio.create_task(tournament_reset_loop())  # ← добавили

async def notify_loop():
    while True:
        now = datetime.utcnow() + timedelta(hours=4)
        if 10 <= now.hour < 22:
            try:
                await notify_max_energy_users()
            except Exception as e:
                api_log.warning("[NOTIFY ERROR] %s", e)
        await asyncio.sleep(3600)









