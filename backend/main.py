from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import json
from pathlib import Path
from datetime import datetime, timedelta
import requests

ENERGY_RECOVERY_INTERVAL_MINUTES = 1
MAX_ENERGY = 100
DAILY_REWARDS = [10, 15, 20, 25, 30, 40, 50]
TELEGRAM_BOT_TOKEN = "7804408659:AAEzVuke_9BSluke6J5tmDInjn5jbh3B5tE"

app = FastAPI()

def extract_user_id(data):
    user_id = str(data.get("user_id") or data.get("id", "")).strip()
    if not user_id or user_id.lower() == "undefined" or user_id == "123456":
        raise ValueError("Недопустимый user_id")
    return user_id

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_FILE = Path("users.json")

if DB_FILE.exists():
    with open(DB_FILE, "r", encoding="utf-8") as f:
        users = json.load(f)
else:
    users = {}

def save_users():
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

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
async def register_user(data: dict):
    try:
        user_id = extract_user_id(data)

        if user_id not in users:
            user_info = get_user_info_from_bot_api(user_id)
            users[user_id] = {
                "id": int(user_id),
                "first_name": user_info.get("first_name", ""),
                "last_name": user_info.get("last_name", ""),
                "username": user_info.get("username", f"id_{user_id}"),
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

    except Exception as e:
        print(f"[REGISTER ERROR] {e}")
        return {"status": "error", "message": str(e)}

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
    try:
        user_id = extract_user_id(data)
        if user_id not in users:
            return {"status": "error", "message": "User not registered"}

        users[user_id]["xp"] = data["xp"]
        users[user_id]["level"] = data["level"]
        users[user_id]["energy"] = data["energy"]
        users[user_id]["total_xp"] = data.get("total_xp", users[user_id].get("total_xp", 0))

        save_users()
        print(f"[SAVED] {user_id} → XP: {data['xp']}, LVL: {data['level']}, ENERGY: {data['energy']}")
        return {"status": "saved"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/game/click")
async def click(data: dict):
    try:
        user_id = extract_user_id(data)
        if user_id in users:
            users[user_id]["total_xp"] += 1
            save_users()
        return {"status": "clicked"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/game/leaderboard")
def leaderboard():
    sorted_users = sorted(users.values(), key=lambda u: u.get("total_xp", 0), reverse=True)
    return [
        {
            "id": u.get("id"),
            "username": (
                u.get("username")
                if u.get("username") and u.get("username") != "undefined"
                else u.get("first_name") or f"user_{u.get('id')}"
            ),
            "total_xp": u.get("total_xp", 0)
        }
        for u in sorted_users
    ]

@app.get("/")
def root():
    return {"status": "ok", "message": "Backend is live!"}

@app.post("/api/admin/clear_users")
def clear_users():
    global users
    users = {}
    save_users()
    return {"status": "cleared"}

@app.get("/api/debug/users")
def get_all_users():
    return users

