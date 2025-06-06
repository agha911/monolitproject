from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import json
from pathlib import Path
from datetime import datetime, timedelta

ENERGY_RECOVERY_INTERVAL_MINUTES = 1  # каждые 5 минут восстанавливается 1 энергия
MAX_ENERGY = 100
DAILY_REWARDS = [10, 15, 20, 25, 30, 40, 50]

app = FastAPI()

# Разрешаем фронтенду обращаться к API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Файл с "базой данных"
DB_FILE = Path("users.json")

# Загружаем базу пользователей из файла
if DB_FILE.exists():
    with open(DB_FILE, "r", encoding="utf-8") as f:
        users = json.load(f)
else:
    users = {}

# Сохраняем базу пользователей в файл
def save_users():
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

@app.post("/api/user/register")
async def register_user(data: dict):
    user_id = str(data["user_id"])
    if user_id not in users:
        users[user_id] = {
            "id": int(user_id),
            "first_name": data.get("first_name", ""),
            "last_name": data.get("last_name", ""),
            "username": data.get("username", ""),
            "score": 0,
            "xp": 0,
            "level": 1,
            "energy": 100,
            "total_xp": 0,
            "max_energy": 100
        }
        print(f"[REGISTERED] {user_id}")
        save_users()
    else:
        print(f"[ALREADY REGISTERED] {user_id}")
    return {"status": "ok"}

@app.get("/api/game/progress/{user_id}")
async def get_progress(user_id: str):
    user = users.get(str(user_id))
    if not user:
        return {
            "xp": 0,
            "level": 1,
            "energy": 100,
            "total_xp": 0,
            "max_energy": 100,
            "lastEnergyUpdate": None,
        }

    now = datetime.utcnow()
    last_update_str = user.get("lastEnergyUpdate")
    max_energy = user.get("max_energy", 100)

    if last_update_str:
        last_update = datetime.fromisoformat(last_update_str)
        minutes_passed = int((now - last_update).total_seconds() // 60)
        energy_to_restore = minutes_passed // ENERGY_RECOVERY_INTERVAL_MINUTES

        if energy_to_restore > 0 and user["energy"] < max_energy:
            user["energy"] = min(max_energy, user["energy"] + energy_to_restore)
            user["lastEnergyUpdate"] = now.isoformat()
            save_users()
    else:
        user["lastEnergyUpdate"] = now.isoformat()
        save_users()

    return {
        "xp": user["xp"],
        "level": user["level"],
        "energy": user["energy"],
        "total_xp": user.get("total_xp", 0),
        "max_energy": max_energy,
        "lastEnergyUpdate": user["lastEnergyUpdate"],
    }


@app.post("/api/game/save_progress")
async def save_progress(data: dict):
    user_id = str(data["user_id"])

    # Если пользователь не найден — создаём его
    if user_id not in users:
        users[user_id] = {
            "first_name": "",
            "last_name": "",
            "username": "",
            "score": 0,
            "xp": 0,
            "level": 1,
            "energy": 100,
            "total_xp": 0
        }

    users[user_id]["xp"] = data["xp"]
    users[user_id]["level"] = data["level"]
    users[user_id]["energy"] = data["energy"]
    users[user_id]["total_xp"] = data.get("total_xp", users[user_id].get("total_xp", 0))

    save_users()
    print(f"[SAVED] {user_id} → XP: {data['xp']}, LVL: {data['level']}, ENERGY: {data['energy']}")
    return {"status": "saved"}


@app.post("/api/game/click")
async def click(data: dict):
    user_id = str(data["user_id"])
    if user_id in users:
        users[user_id]["total_xp"] += 1
        save_users()
    return {"status": "clicked"}



@app.get("/api/game/leaderboard")
def leaderboard():
    sorted_users = sorted(users.values(), key=lambda u: u.get("total_xp", 0), reverse=True)
    return [
        {
            "id": u.get("id"),
            "username": u.get("username") or f"id_{u.get('id')}",
            "total_xp": u.get("total_xp", 0)
        }
        for u in sorted_users
    ]

@app.post("/api/shop/buy_max_energy")
def buy_max_energy(data: dict):
    user_id = str(data["user_id"])
    user = users.get(user_id)

    if not user:
        return {"status": "error", "message": "User not found"}

    if user["total_xp"] < 50:
        return {"status": "error", "message": "Not enough MONO"}

    user["total_xp"] -= 50
    user["max_energy"] = user.get("max_energy", 100) + 100
    save_users()
    return {"status": "success", "new_max_energy": user["max_energy"], "remaining_mono": user["total_xp"]}


@app.post("/api/task/complete")
def complete_task(data: dict):
    user_id = str(data["user_id"])
    task_id = data.get("task_id")

    if not task_id or task_id != "follow_instagram":
        return {"status": "error", "message": "Invalid task"}

    user = users.get(user_id)
    if not user:
        return {"status": "error", "message": "User not found"}

    # Защита от повторного выполнения
    if "completed_tasks" not in user:
        user["completed_tasks"] = []

    if task_id in user["completed_tasks"]:
        return {"status": "already_completed"}

    # Выполняем задание
    user["completed_tasks"].append(task_id)
    user["total_xp"] += 50
    save_users()

    return {"status": "success", "reward": 50}


@app.post("/api/task/daily_checkin")
def daily_checkin(data: dict):
    user_id = str(data["user_id"])
    user = users.get(user_id)

    if not user:
        return {"status": "error", "message": "User not found"}

    now = datetime.utcnow()
    last_checkin_str = user.get("last_checkin")
    last_checkin = datetime.fromisoformat(last_checkin_str) if last_checkin_str else None
    streak = user.get("daily_streak", 0)

    if last_checkin and (now - last_checkin) < timedelta(hours=24):
        return {"status": "already_checked_in", "day": streak, "reward": DAILY_REWARDS[streak - 1]}

    # Сбросить, если прошло больше 48ч
    if last_checkin and (now - last_checkin) > timedelta(hours=48):
        streak = 0

    # Увеличиваем прогресс
    streak = min(streak + 1, len(DAILY_REWARDS))
    reward = DAILY_REWARDS[streak - 1]

    user["daily_streak"] = streak
    user["last_checkin"] = now.isoformat()
    user["total_xp"] = user.get("total_xp", 0) + reward

    save_users()

    return {
        "status": "success",
        "day": streak,
        "reward": reward,
        "next_reset_utc": (now + timedelta(hours=24)).isoformat()
    }

@app.get("/")
def root():
    return {"status": "ok", "message": "Backend is live!"}