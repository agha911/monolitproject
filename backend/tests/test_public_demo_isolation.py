from contextlib import asynccontextmanager
import asyncio
import os
import pytest

from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.testclient import TestClient

from test_auth import TOKEN
from test_gameplay import game  # noqa: F401 -- isolated database guard and model setup
from app.public_demo_gateway import COOKIE, PublicDemoGateway
from app.public_demo_sessions import CURRENT_SANDBOX, DemoSessions

ORIGIN = "http://127.0.0.1"


def test_real_visitors_have_separate_progress_capacity_and_expiry(game):
    client, _ = game
    from app.main import app
    from app.database import get_async_session
    now = [0]
    sessions = DemoSessions(os.environ["TEST_DATABASE_URL"], TOKEN, maximum=2, lifetime=60, clock=lambda: now[0])

    @asynccontextmanager
    async def lifespan(application):
        await sessions.start()
        yield
        await sessions.close()

    async def isolated_database():
        async with CURRENT_SANDBOX.get().maker() as db:
            yield db

    previous = app.dependency_overrides[get_async_session]
    app.dependency_overrides[get_async_session] = isolated_database
    boundary = PublicDemoGateway(Starlette(routes=[Mount("/", app)], lifespan=lifespan), sessions, ORIGIN)
    try:
        with TestClient(boundary, base_url=ORIGIN) as browser:
            def login():
                response = browser.post("/demo/session", headers={"Origin": ORIGIN})
                assert response.status_code == 200, response.text
                return browser.cookies[COOKIE], response.json()["init_data"]

            first_cookie, first = login()
            headers = {"Origin": ORIGIN, "X-Telegram-Init-Data": first}
            result = browser.post("/api/game/clicks/flush", headers=headers,
                json={"init_data": first, "delta_clicks": 20, "client_seq": 1, "session_id": "public-test"})
            assert result.status_code == 200, result.text
            assert result.json()["total_xp"] == 12020
            reward = browser.post("/api/daily/claim_reward", headers=headers, json={"init_data": first})
            assert reward.json()["status"] == "reward_claimed"
            browser.cookies.clear()
            second_cookie, second = login()
            second_headers = {"Origin": ORIGIN, "X-Telegram-Init-Data": second}
            progress = browser.post("/api/game/progress", headers=second_headers, json={"init_data": second})
            assert progress.json()["total_xp"] == 12000
            assert progress.json()["daily_reward_claimed"] is False
            assert browser.get("/api/game/leaderboard", headers=second_headers).json()[0]["total_xp"] == 18500
            assert browser.get("/api/game/leaderboard", headers=headers).status_code == 401
            browser.cookies.clear()
            assert browser.post("/demo/session", headers={"Origin": ORIGIN}).status_code == 503
            browser.cookies.set(COOKIE, first_cookie, domain="127.0.0.1", path="/")
            progress = browser.post("/api/game/progress", headers=headers, json={"init_data": first})
            assert progress.json()["total_xp"] == 62020
            now[0] = 61
            assert browser.get("/api/game/leaderboard", headers=headers).status_code == 401
            # Creation prunes expired sandboxes before allocating replacement capacity.
            new_cookie, new_credential = login()
            assert new_cookie not in {first_cookie, second_cookie}
            assert new_credential not in {first, second}
            assert len(sessions.entries) == 1
    finally:
        app.dependency_overrides[get_async_session] = previous
    assert sessions.entries == {}


def test_active_lease_defers_cleanup_and_second_worker_is_rejected(game):
    async def action():
        now = [0]
        first = DemoSessions(os.environ["TEST_DATABASE_URL"], TOKEN, lifetime=60, clock=lambda: now[0])
        second = DemoSessions(os.environ["TEST_DATABASE_URL"], TOKEN)
        await first.start()
        try:
            with pytest.raises(RuntimeError, match="exactly one worker"):
                await second.start()
            cookie, entry = await first.session()
            async with first.acquire(cookie, entry.init_data) as lease:
                assert lease is entry
                now[0] = 61
                await first.prune()
                assert cookie in first.entries
            await first.prune()
            assert first.entries == {}
            with pytest.raises(ValueError, match="non-demo schema"):
                await first._drop("public")
        finally:
            await second.close()
            await first.close()
    asyncio.run(action())
