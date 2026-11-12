import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from app.public_demo_gateway import COOKIE, PublicDemoGateway, WindowLimiter, validate_origin
from app.public_demo_sessions import CURRENT_SANDBOX

ORIGIN = "https://demo.example"


class FakeSessions:
    lifetime = 1200
    clock = staticmethod(lambda: 0)

    def __init__(self):
        self.entries = {}

    async def session(self, cookie):
        if cookie not in self.entries:
            cookie = "cookie-" + str(len(self.entries))
            self.entries[cookie] = SimpleNamespace(schema=cookie, init_data="signed-" + cookie, expires=1200)
        return cookie, self.entries[cookie]

    @asynccontextmanager
    async def acquire(self, cookie, credential):
        entry = self.entries.get(cookie)
        yield entry if entry and entry.init_data == credential else None


async def echo(scope, receive, send):
    entry = CURRENT_SANDBOX.get()
    await JSONResponse({"sandbox": entry.schema if entry else None})(scope, receive, send)


@pytest.fixture
def client():
    return TestClient(PublicDemoGateway(echo, FakeSessions(), ORIGIN), base_url=ORIGIN)


def login(client):
    response = client.post("/demo/session", headers={"Origin": ORIGIN})
    assert response.status_code == 200, response.text
    return response.json()["init_data"]


def test_session_requires_origin_and_sets_private_cookie(client):
    assert client.get("/demo/session").status_code == 404
    assert client.post("/demo/session").status_code == 403
    response = client.post("/demo/session", headers={"Origin": ORIGIN})
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "secure" in cookie and "httponly" in cookie and "samesite=strict" in cookie
    assert response.headers["cache-control"] == "no-store"


def test_cookie_and_signed_credential_must_belong_to_same_visitor(client):
    first = login(client)
    response = client.get("/api/game/leaderboard", headers={"X-Telegram-Init-Data": first})
    assert response.json()["sandbox"] == "cookie-0"
    assert CURRENT_SANDBOX.get() is None
    client.cookies.clear()
    second = login(client)
    assert first != second
    assert client.get("/api/game/leaderboard", headers={"X-Telegram-Init-Data": first}).status_code == 401
    assert client.get("/api/game/leaderboard", headers={"X-Telegram-Init-Data": second}).json()["sandbox"] == "cookie-1"
    assert client.get("/api/game/leaderboard").status_code == 401
    client.cookies.clear()
    assert client.get("/api/game/leaderboard", headers={"X-Telegram-Init-Data": second}).status_code == 401


@pytest.mark.parametrize("path", ["/api/pvp/admin/reset-weekly", "/api/partner/redeem", "/api/drops/buy",
    "/api/task/complete", "/api/pvp/invite/create", "/api/pvp/matchmaking/join", "/api/dao/proposals/1/vote"])
def test_sensitive_routes_are_unavailable_even_with_a_session(client, path):
    credential = login(client)
    assert client.post(path, headers={"Origin": ORIGIN, "X-Telegram-Init-Data": credential}, json={}).status_code == 404


def test_origin_body_and_url_bounds(client):
    credential = login(client)
    headers = {"Origin": ORIGIN, "X-Telegram-Init-Data": credential}
    assert client.post("/api/game/progress", headers={**headers, "Origin": "https://other.example"}, json={}).status_code == 403
    assert client.get("/api/game/leaderboard", headers={**headers, "Origin": "https://other.example"}).status_code == 403
    assert client.post("/api/game/progress", headers=headers, content=b"x" * 16385).status_code == 413
    assert client.get("/api/game/leaderboard?x=" + "x" * 4096, headers=headers).status_code == 414


def test_chunked_body_limit_does_not_trust_content_length():
    async def action():
        gateway = PublicDemoGateway(echo, FakeSessions(), ORIGIN)
        chunks = iter([{"type": "http.request", "body": b"x" * 6000, "more_body": more}
                       for more in (True, True, False)])
        responses = []

        async def receive():
            return next(chunks)

        async def send(message):
            responses.append(message)

        await gateway({"type": "http", "path": "/api/game/progress", "method": "POST",
            "headers": [(b"origin", ORIGIN.encode()), (b"content-length", b"1")],
            "query_string": b"", "client": ("127.0.0.1", 123)}, receive, send)
        assert responses[0]["status"] == 413
    asyncio.run(action())


def test_creation_limit_ignores_forged_forwarding_headers(client):
    for index in range(4):
        client.cookies.clear()
        response = client.post("/demo/session", headers={"Origin": ORIGIN, "X-Forwarded-For": f"10.0.0.{index}"})
        assert response.status_code == (200 if index < 3 else 429)
    assert response.headers["retry-after"] == "60"


def test_limiter_window_recovers_and_memory_is_bounded():
    now = [0]
    limiter = WindowLimiter(clock=lambda: now[0], maximum_keys=4)
    assert limiter.allow("visitor", 1)
    assert not limiter.allow("visitor", 1)
    now[0] = 61
    assert limiter.allow("visitor", 1)
    for index in range(20):
        limiter.allow(str(index), 1)
    assert len(limiter.entries) == 4


@pytest.mark.parametrize("origin", ["", "http://demo.example", "https://user:pass@demo.example", "https://demo.example/path", "https://demo.example?x=1"])
def test_public_origin_rejects_insecure_or_ambiguous_configuration(origin):
    with pytest.raises(ValueError):
        validate_origin(origin)
