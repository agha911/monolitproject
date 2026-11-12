"""Isolated visitor-demo candidate. Hosting must be configured separately."""
import asyncio
import importlib
import logging
import os
import pkgutil
import secrets
from pathlib import Path

from dotenv import load_dotenv
from fastapi import HTTPException
from sqlalchemy.engine import make_url

from app.public_demo_gateway import PublicDemoGateway, validate_origin
from app.public_demo_sessions import CURRENT_SANDBOX, DemoSessions
from app.browser_site import create_browser_site

load_dotenv()
origin = validate_origin(os.environ.get("DEMO_PUBLIC_ORIGIN", ""))
url = make_url(os.environ.get("DATABASE_URL", ""))
allowed = {"127.0.0.1", "localhost", "::1"}
if os.getenv("MONOLIT_DEMO_CONTAINER") == "true":
    allowed.add("db")
if url.host not in allowed or url.database != "monolit_demo" or url.drivername != "postgresql+asyncpg":
    raise RuntimeError("Visitor demo requires the dedicated monolit_demo database on loopback or Compose db")

# Generated per process; never the known local-demo token or a real Telegram token.
token = "123456789:" + secrets.token_urlsafe(32)
os.environ["TELEGRAM_BOT_TOKEN"] = token
os.environ["CORS_ORIGINS"] = origin
for flag in ("ENABLE_BOT_POLLING", "ENABLE_NOTIFICATIONS", "ENABLE_SEASON_WORKER",
             "ENABLE_HISTORICAL_FINALIZER", "ALLOW_TELEGRAM_LOOKUPS"):
    os.environ[flag] = "false"

from app.main import app as api_app  # noqa: E402
from app.database import get_async_session  # noqa: E402
from app import models  # noqa: E402

sessions = DemoSessions(url, token)
cleanup_task = None


async def isolated_database():
    entry = CURRENT_SANDBOX.get()
    if entry is None:
        raise HTTPException(401, "Demo session required")
    async with entry.maker() as db:
        yield db


api_app.dependency_overrides[get_async_session] = isolated_database


@api_app.on_event("startup")
async def start_visitors():
    global cleanup_task
    for module in pkgutil.iter_modules(models.__path__):
        importlib.import_module(f"app.models.{module.name}")
    await sessions.start()

    async def cleanup():
        while True:
            await asyncio.sleep(30)
            try:
                await sessions.prune()
            except Exception:
                logging.getLogger(__name__).error("Temporary demo cleanup failed; will retry")
    cleanup_task = asyncio.create_task(cleanup())


@api_app.on_event("shutdown")
async def stop_visitors():
    if cleanup_task:
        cleanup_task.cancel()
        await asyncio.gather(cleanup_task, return_exceptions=True)
    await sessions.close()


directory = os.getenv("FRONTEND_DIST", str(Path(__file__).resolve().parents[2] / "frontend" / "dist"))
site = create_browser_site(PublicDemoGateway(api_app, sessions, origin), directory)


async def app(scope, receive, send):
    async def secure_send(message):
        if message["type"] == "http.response.start":
            headers = list(message.get("headers", []))
            headers.extend([
                (b"x-frame-options", b"DENY"), (b"x-content-type-options", b"nosniff"),
                (b"referrer-policy", b"no-referrer"),
                (b"content-security-policy", b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"),
            ])
            if origin.startswith("https:"):
                headers.append((b"strict-transport-security", b"max-age=31536000"))
            message = {**message, "headers": headers}
        await send(message)
    await site(scope, receive, secure_send)
