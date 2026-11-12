"""Bounded, disposable PostgreSQL sandboxes for a single public-demo process."""
import asyncio
import hashlib
import hmac
import json
import re
import secrets
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlencode

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

PREFIX = "monolit_public_"
SCHEMA = re.compile(r"monolit_public_[0-9a-f]{32}\Z")
CURRENT_SANDBOX = ContextVar("public_demo_sandbox", default=None)


class DemoCapacity(Exception):
    pass


@dataclass
class Sandbox:
    schema: str
    engine: AsyncEngine
    maker: sessionmaker
    init_data: str
    expires: float
    active: int = 0


class DemoSessions:
    def __init__(self, url, token, *, maximum=12, lifetime=1200, clock=time.monotonic):
        self.url, self.token = url, token
        self.maximum, self.lifetime, self.clock = maximum, lifetime, clock
        self.entries: dict[str, Sandbox] = {}
        self.lock = asyncio.Lock()
        self.admin = create_async_engine(url, poolclass=NullPool)
        self.owner_connection = None

    async def start(self):
        # Prevent a second worker/replica from removing the first one's sandboxes.
        self.owner_connection = await self.admin.connect()
        locked = (await self.owner_connection.execute(text("SELECT pg_try_advisory_lock(7246112001)"))).scalar_one()
        if not locked:
            await self.owner_connection.close()
            self.owner_connection = None
            raise RuntimeError("Public demo requires exactly one worker and one replica")
        names = (await self.owner_connection.execute(text(
            "SELECT nspname FROM pg_namespace WHERE left(nspname, length(:prefix)) = :prefix"
        ), {"prefix": PREFIX})).scalars().all()
        await self.owner_connection.commit()
        for name in names:
            if SCHEMA.fullmatch(name):
                await self._drop(name)

    async def _drop(self, schema):
        if not SCHEMA.fullmatch(schema):
            raise ValueError("Refusing to drop a non-demo schema")
        async with self.admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))

    async def _prune(self):
        for cookie, entry in list(self.entries.items()):
            if entry.expires <= self.clock() and entry.active == 0:
                await self._drop(entry.schema)
                await entry.engine.dispose()
                del self.entries[cookie]

    async def prune(self):
        async with self.lock:
            await self._prune()

    async def session(self, cookie=None):
        async with self.lock:
            await self._prune()
            existing = self.entries.get(cookie)
            if existing and existing.expires > self.clock():
                return cookie, existing
            if len(self.entries) >= self.maximum:
                raise DemoCapacity()
            schema = PREFIX + secrets.token_hex(16)
            engine = create_async_engine(self.url, poolclass=NullPool,
                connect_args={"server_settings": {"search_path": schema,
                    "statement_timeout": "5000", "lock_timeout": "2000", "idle_in_transaction_session_timeout": "10000"}})
            try:
                async with self.admin.begin() as connection:
                    await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
                from app.database import Base
                from app.models.user import User
                async with engine.begin() as connection:
                    await connection.run_sync(Base.metadata.create_all)
                maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                async with maker() as db:
                    for tid, name, coins in ((900000001, "Demo Explorer", 12000),
                                              (900000002, "Pixel Pilot", 18500),
                                              (900000003, "Code Comet", 15200)):
                        db.add(User(telegram_id=tid, first_name=name, username=name.replace(" ", "_"),
                            total_xp=coins, energy=1000, max_energy=1000, lastEnergyUpdate=now,
                            daily_target=20, daily_progress=0, daily_completed=False,
                            daily_updated_at=now, pvp_best_result=100))
                    await db.commit()
                cookie = secrets.token_urlsafe(32)
                data = {"auth_date": str(int(time.time())), "query_id": secrets.token_urlsafe(24),
                    "user": json.dumps({"id": 900000001, "first_name": "Demo Explorer"})}
                secret = hmac.new(b"WebAppData", self.token.encode(), hashlib.sha256).digest()
                data["hash"] = hmac.new(secret, "\n".join(f"{k}={v}" for k, v in sorted(data.items())).encode(), hashlib.sha256).hexdigest()
                entry = Sandbox(schema, engine, maker, urlencode(data), self.clock() + self.lifetime)
                self.entries[cookie] = entry
                return cookie, entry
            except BaseException:
                await engine.dispose()
                await self._drop(schema)
                raise

    @asynccontextmanager
    async def acquire(self, cookie, credential):
        async with self.lock:
            entry = self.entries.get(cookie)
            if not entry or entry.expires <= self.clock() or not hmac.compare_digest(entry.init_data.encode(), credential.encode()):
                entry = None
            elif entry.active >= 8:
                raise DemoCapacity()
            else:
                entry.active += 1
        try:
            yield entry
        finally:
            if entry:
                async with self.lock:
                    entry.active -= 1

    async def close(self):
        async with self.lock:
            for entry in self.entries.values():
                await self._drop(entry.schema)
                await entry.engine.dispose()
            self.entries.clear()
        if self.owner_connection:
            await self.owner_connection.execute(text("SELECT pg_advisory_unlock(7246112001)"))
            await self.owner_connection.close()
            self.owner_connection = None
        await self.admin.dispose()
