"""Telegram Mini App authentication; never trust client-supplied user IDs."""
import hashlib
import hmac
import json
import os
import time
from urllib.parse import parse_qsl

from fastapi import HTTPException, Request


def validate_init_data(raw: str, *, bot_token: str | None = None,
                       now: float | None = None, max_age: int = 3600) -> int:
    token = bot_token if bot_token is not None else os.getenv("TELEGRAM_BOT_TOKEN", "")
    try:
        if not token or not isinstance(raw, str) or not raw or len(raw) > 16384:
            raise ValueError()
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True)
        data = dict(pairs)
        if len(pairs) != len(data):
            raise ValueError()
        supplied_hash = data.pop("hash")
        check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
        secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, supplied_hash):
            raise ValueError()
        age = (time.time() if now is None else now) - int(data["auth_date"])
        if age < -30 or age > max_age:
            raise ValueError()
        user_id = json.loads(data["user"])["id"]
        if type(user_id) is not int or user_id <= 0:
            raise ValueError()
        return user_id
    except (ValueError, TypeError, KeyError, OverflowError):
        raise HTTPException(status_code=401, detail="Invalid or expired Telegram authentication") from None


# Existing endpoints below authenticate with their own partner/admin secrets.
SEPARATE_AUTH = {
    "/api/partner/purchases", "/api/partner/redeem", "/api/partner/revoke",
    "/api/pvp/admin/reset-weekly", "/api/pvp/admin/weekly/rollover",
}


async def require_telegram_user(request: Request) -> None:
    path = request.url.path.rstrip("/")
    if not path.startswith("/api/") or path in SEPARATE_AUTH:
        return
    if "/admin/" in path:
        admin_key = os.getenv("MONOLIT_ADMIN_KEY", "")
        if not admin_key or not hmac.compare_digest(request.headers.get("X-Admin-Key", "").encode(), admin_key.encode()):
            raise HTTPException(status_code=403, detail="Administrator access required")
    body = {}
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(status_code=400, detail="Expected JSON body") from None
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Expected JSON object")
    credentials = [request.headers.get("X-Telegram-Init-Data"), request.headers.get("init-data")]
    credentials.extend(request.query_params.getlist("init_data"))
    credentials.extend(request.query_params.getlist("initData"))
    credentials.extend(body.get(k) for k in ("init_data", "initData") if k in body)
    present = [value for value in credentials if value]
    if not present:
        raise HTTPException(status_code=401, detail="Telegram authentication required")
    identities = [validate_init_data(value) for value in present]
    user_id = identities[0]
    if any(value != user_id for value in identities):
        raise HTTPException(status_code=403, detail="Conflicting Telegram identities")
    claimed = request.query_params.getlist("telegram_id")
    if "telegram_id" in body:
        claimed.append(body["telegram_id"])
    if path.startswith("/api/task/") and "user_id" in body:
        claimed.append(body["user_id"])  # legacy field contains a Telegram ID
    if request.headers.get("X-Telegram-User-Id"):
        claimed.append(request.headers["X-Telegram-User-Id"])
    for value in claimed:
        if isinstance(value, bool) or str(value) != str(user_id):
            raise HTTPException(status_code=403, detail="User ID does not match authenticated user")
    request.state.telegram_user_id = user_id
