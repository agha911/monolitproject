"""Isolated portfolio demo entry point. Never deploy against a real database."""
import hashlib
import hmac
import json
import os
import time
from datetime import datetime
from urllib.parse import urlencode

from dotenv import load_dotenv
from sqlalchemy.engine import make_url

load_dotenv()
url = make_url(os.getenv("DATABASE_URL", "postgresql+asyncpg://monolit@127.0.0.1:55432/monolit_demo"))
if url.host not in {"127.0.0.1", "localhost", "::1"} or url.database != "monolit_demo":
    raise RuntimeError("Demo requires a loopback database named monolit_demo")
os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)
# A dedicated, intentionally non-secret demo identity. Never reuse a real bot token.
DEMO_TOKEN = "123456789:monolit-local-portfolio-demo"
os.environ["TELEGRAM_BOT_TOKEN"] = DEMO_TOKEN
for name in ("ENABLE_BOT_POLLING", "ENABLE_NOTIFICATIONS", "ENABLE_SEASON_WORKER",
             "ENABLE_HISTORICAL_FINALIZER", "ALLOW_TELEGRAM_LOOKUPS"):
    os.environ[name] = "false"

from app.main import app  # noqa: E402
from app.database import async_session_maker  # noqa: E402
from app.init_db import init_models  # noqa: E402
from app.models.user import User  # noqa: E402
from sqlalchemy import select  # noqa: E402


@app.on_event("startup")
async def seed_demo():
    await init_models()
    async with async_session_maker() as session:
        for tid, name, coins in ((900000001, "Demo Explorer", 12000),
                                 (900000002, "Pixel Pilot", 18500),
                                 (900000003, "Code Comet", 15200)):
            existing = (await session.execute(select(User).where(User.telegram_id == tid))).scalar_one_or_none()
            if existing is None:
                session.add(User(telegram_id=tid, first_name=name, username=name.replace(" ", "_"),
                                 total_xp=coins, energy=1000, max_energy=1000,
                                 lastEnergyUpdate=datetime.utcnow(), daily_target=20,
                                 daily_progress=0, daily_completed=False,
                                 daily_updated_at=datetime.utcnow(), pvp_best_result=100))
        await session.commit()


@app.get("/demo/session")
async def demo_session():
    data = {"auth_date": str(int(time.time())), "user": json.dumps({"id": 900000001, "first_name": "Demo Explorer"})}
    secret = hmac.new(b"WebAppData", DEMO_TOKEN.encode(), hashlib.sha256).digest()
    data["hash"] = hmac.new(secret, "\n".join(f"{k}={v}" for k, v in sorted(data.items())).encode(), hashlib.sha256).hexdigest()
    return {"init_data": urlencode(data), "telegram_id": 900000001, "name": "Demo Explorer"}
