"""Public-demo boundary: a small allowlist, same-origin sessions and bounded traffic."""
import asyncio
import time
from collections import OrderedDict, deque
from http.cookies import SimpleCookie
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import JSONResponse

from app.public_demo_sessions import CURRENT_SANDBOX, DemoCapacity

COOKIE = "monolit_demo_session"
READS = {
    "/api/game/leaderboard", "/api/user/count", "/api/user/invites", "/api/user/card",
    "/api/referral/balance", "/api/stats/total-spent", "/api/drops",
    "/api/shop/buy_max_energy/status", "/api/shop/buy_energy_refill/status", "/api/shop/tshirt/status",
    "/api/pvp/config", "/api/pvp/me", "/api/pvp/leaderboard", "/api/pvp/weekly-season/current",
    "/api/pvp/weekly-season/leaderboard", "/api/pvp/challenge/status",
}
WRITES = {
    "/api/user/register", "/api/game/progress", "/api/game/clicks/flush", "/api/daily/claim_reward",
    "/api/task/daily", "/api/task/daily_checkin", "/api/referral/claim",
    "/api/shop/buy_max_energy", "/api/shop/buy_energy_refill", "/api/shop/buy_click_boost",
    "/api/boosters/claim/coins", "/api/boosters/claim/multiplier",
    "/api/pvp/challenge/start", "/api/pvp/challenge/finish",
}


def validate_origin(origin):
    value = urlsplit(origin)
    try:
        value.port
    except ValueError:
        raise ValueError("DEMO_PUBLIC_ORIGIN has an invalid port") from None
    local = value.hostname in {"localhost", "127.0.0.1", "::1"}
    if (value.scheme not in {"http", "https"} or (value.scheme == "http" and not local)
            or not value.hostname or value.username or value.password or value.path
            or value.query or value.fragment or origin != f"{value.scheme}://{value.netloc}"):
        raise ValueError("DEMO_PUBLIC_ORIGIN must be an HTTPS origin (HTTP is allowed only on loopback)")
    return origin


class WindowLimiter:
    def __init__(self, clock=time.monotonic, maximum_keys=2048):
        self.clock, self.maximum_keys = clock, maximum_keys
        self.entries = OrderedDict()

    def allow(self, key, limit, window=60):
        now = self.clock()
        values = self.entries.pop(key, deque())
        while values and values[0] <= now - window:
            values.popleft()
        allowed = len(values) < limit
        if allowed:
            values.append(now)
        self.entries[key] = values
        while len(self.entries) > self.maximum_keys:
            self.entries.popitem(last=False)
        return allowed


class PublicDemoGateway:
    def __init__(self, app, sessions, origin, *, limiter=None):
        self.app, self.sessions = app, sessions
        self.origin = validate_origin(origin)
        self.secure = origin.startswith("https:")
        self.limiter = limiter or WindowLimiter()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def guarded_send(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend([(b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"), (b"vary", b"Cookie")])
                message = {**message, "headers": headers}
            await send(message)

        async def reject(status, detail):
            response = JSONResponse({"detail": detail}, status_code=status,
                headers={"Retry-After": "60"} if status in {429, 503} else {})
            await response(scope, receive, guarded_send)

        path, method = scope["path"], scope["method"]
        request = Request(scope)
        if method == "GET" and path == "/":  # /health is mapped here by the browser-site wrapper.
            await self.app(scope, receive, guarded_send)
            return
        bootstrap = path == "/demo/session" and method == "POST"
        if not bootstrap and not ((method == "GET" and path in READS) or (method == "POST" and path in WRITES)):
            await reject(404, "This operation is unavailable in the portfolio demo")
            return
        if len(scope.get("query_string", b"")) > 4096:
            await reject(414, "Request URL too long")
            return
        origin = request.headers.get("origin")
        if (method == "POST" and origin != self.origin) or (origin and origin != self.origin):
            await reject(403, "Same-origin requests required")
            return
        # Deliberately ignore X-Forwarded-For; proxy trust is configured at deployment.
        peer = scope.get("client") or ("unknown", 0)
        if not self.limiter.allow("all", 2400):
            await reject(429, "Demo request limit reached")
            return
        body = b""
        if method == "POST":
            try:
                async with asyncio.timeout(5):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        body += message.get("body", b"")
                        if len(body) > 16384:
                            await reject(413, "Demo request body too large")
                            return
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                await reject(408, "Request body timeout")
                return
        try:
            cookies = SimpleCookie(request.headers.get("cookie", ""))
            cookie = cookies[COOKIE].value if COOKIE in cookies else None
        except Exception:
            cookie = None
        if cookie and len(cookie) > 128:
            await reject(401, "Invalid demo session")
            return
        if bootstrap:
            if not self.limiter.allow("bootstrap:" + peer[0], 12):
                await reject(429, "Too many demo session requests")
                return
            # Creation is separately limited; existing sessions do not consume new slots.
            if cookie not in self.sessions.entries and not self.limiter.allow("create:" + peer[0], 3):
                await reject(429, "Too many new demo sessions")
                return
            try:
                cookie, entry = await self.sessions.session(cookie)
            except DemoCapacity:
                await reject(503, "The demo is busy. Please try again shortly")
                return
            response = JSONResponse({"init_data": entry.init_data, "telegram_id": 900000001,
                "name": "Demo Explorer", "expires_in": max(0, int(entry.expires - self.sessions.clock()))})
            response.set_cookie(COOKIE, cookie, max_age=self.sessions.lifetime, secure=self.secure,
                httponly=True, samesite="strict", path="/")
            await response(scope, receive, guarded_send)
            return
        if not self.limiter.allow("session:" + str(cookie), 600):
            await reject(429, "Please slow down and try again shortly")
            return
        try:
            async with self.sessions.acquire(cookie, request.headers.get("x-telegram-init-data", "")) as entry:
                if entry is None:
                    await reject(401, "Demo session expired. Reload to start a new demo")
                    return
                context = CURRENT_SANDBOX.set(entry)
                consumed = False

                async def replay():
                    nonlocal consumed
                    if not consumed:
                        consumed = True
                        return {"type": "http.request", "body": body, "more_body": False}
                    return await receive()

                try:
                    await self.app(scope, replay, guarded_send)
                finally:
                    CURRENT_SANDBOX.reset(context)
        except DemoCapacity:
            await reject(429, "Too many simultaneous demo requests")
