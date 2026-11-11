"""Real PostgreSQL regression tests, each in its own disposable schema."""
import asyncio
import importlib
import os
import pkgutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from test_auth import TOKEN, signed


@pytest.fixture
def game(monkeypatch):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a dedicated monolit_test database")
    parsed = make_url(url)
    if parsed.host not in {"127.0.0.1", "localhost", "::1"} or parsed.database != "monolit_test":
        pytest.fail("Integration tests require a loopback database named monolit_test")
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    for name in ("ENABLE_BOT_POLLING", "ENABLE_NOTIFICATIONS", "ENABLE_SEASON_WORKER",
                 "ENABLE_HISTORICAL_FINALIZER", "ALLOW_TELEGRAM_LOOKUPS"):
        monkeypatch.setenv(name, "false")
    from app.main import app
    from app.database import Base, get_async_session
    from app import models
    for module in pkgutil.iter_modules(models.__path__):
        importlib.import_module(f"app.models.{module.name}")
    schema = "test_" + uuid.uuid4().hex
    admin = create_async_engine(url, poolclass=NullPool)
    engine = create_async_engine(url, poolclass=NullPool, connect_args={"server_settings": {"search_path": schema}})
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with admin.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def session_override():
        async with maker() as session:
            yield session

    asyncio.run(setup())
    app.dependency_overrides[get_async_session] = session_override
    try:
        with TestClient(app) as client:
            yield client, maker
    finally:
        app.dependency_overrides.pop(get_async_session, None)

        async def teardown():
            await engine.dispose()
            async with admin.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            await admin.dispose()
        asyncio.run(teardown())


def seed(maker, **values):
    async def action():
        from app.models.user import User
        async with maker() as session:
            user = User(telegram_id=101, total_xp=10000, energy=100, max_energy=1000,
                        lastEnergyUpdate=datetime.utcnow(), **values)
            session.add(user)
            await session.commit()
    asyncio.run(action())


def user_state(maker):
    async def action():
        from app.models.user import User
        async with maker() as session:
            return (await session.execute(select(User).where(User.telegram_id == 101))).scalar_one()
    return asyncio.run(action())


def test_registration_is_idempotent(game):
    client, maker = game
    for expected in ("ok", "already_registered"):
        response = client.post("/api/user/register", json={"init_data": signed()})
        assert response.status_code == 200, response.text
        assert response.json()["status"] == expected
    assert user_state(maker).telegram_id == 101


def test_click_flush_does_not_double_credit(game):
    client, maker = game
    seed(maker, daily_target=50)
    payload = {"init_data": signed(), "delta_clicks": 40, "client_seq": 1, "session_id": "test-session"}
    results = [client.post("/api/game/clicks/flush", json=payload).json() for _ in range(2)]
    assert [r["accepted_clicks"] for r in results] == [40, 0], results
    state = user_state(maker)
    assert state.total_xp == 10040
    assert state.energy == 60
    progress = client.post("/api/game/progress", json={"init_data": signed()}).json()
    assert progress["daily_progress"] == 40


def test_daily_reward_is_awarded_once_under_concurrency(game):
    client, maker = game
    seed(maker, daily_completed=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: client.post("/api/daily/claim_reward", json={"init_data": signed()}).json(), range(4)))
    assert sum(r.get("status") == "reward_claimed" for r in results) == 1, results
    assert user_state(maker).total_xp == 60000


def test_energy_purchase_obeys_daily_limit_under_concurrency(game):
    client, maker = game
    seed(maker)
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(lambda _: client.post("/api/shop/buy_max_energy", json={"telegram_id": 101},
                                 headers={"X-Telegram-Init-Data": signed()}), range(3)))
    assert sorted(r.status_code for r in responses) == [200, 200, 400], [r.text for r in responses]
    state = user_state(maker)
    assert state.total_xp == 5000
    assert state.max_energy == 3000


def test_drop_purchase_obeys_supply_and_balance(game):
    client, maker = game
    seed(maker)

    async def offer():
        from app.models.partner import Partner
        from app.models.drop import Drop
        async with maker() as session:
            partner = Partner(name="Synthetic Partner", slug="synthetic", partner_balance=0)
            session.add(partner)
            await session.flush()
            now = datetime.now(timezone.utc)
            drop = Drop(partner_id=partner.id, title="Test offer", discount_percent=10,
                        start_at=now-timedelta(days=1), end_at=now+timedelta(days=1),
                        price_coins=1000, per_user_limit=1, total_supply=1, active=True, visible=True)
            session.add(drop)
            await session.commit()
            return drop.id
    drop_id = asyncio.run(offer())
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post("/api/drops/buy", json={"telegram_id": 101, "drop_id": drop_id},
                                 headers={"X-Telegram-Init-Data": signed()}), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 400], [r.text for r in responses]
    assert user_state(maker).total_xp == 9000


def test_purchases_by_different_users_preserve_total_spent(game):
    client, maker = game
    seed(maker)

    async def second_user():
        from app.models.user import User
        async with maker() as session:
            session.add(User(telegram_id=202, total_xp=10000, energy=100, max_energy=1000))
            await session.commit()
    asyncio.run(second_user())
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda tid: client.post("/api/shop/buy_max_energy", json={"telegram_id": tid},
                                 headers={"X-Telegram-Init-Data": signed(tid)}), (101, 202)))
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]

    async def total():
        from app.models.app_stats import AppStats
        async with maker() as session:
            return (await session.execute(select(AppStats.total_spent).where(AppStats.id == 1))).scalar_one()
    assert asyncio.run(total()) == 5000


def test_pvp_challenge_daily_limit(game):
    client, maker = game
    seed(maker, pvp_best_result=100)

    async def opponent():
        from app.models.user import User
        async with maker() as session:
            session.add(User(telegram_id=202, total_xp=10000, pvp_best_result=100))
            await session.commit()
    asyncio.run(opponent())
    responses = [client.post("/api/pvp/challenge/start", json={"telegram_id": 101},
                            headers={"X-Telegram-Init-Data": signed()}) for _ in range(6)]
    assert [r.status_code for r in responses] == [200, 200, 200, 200, 200, 409], [r.text for r in responses]
