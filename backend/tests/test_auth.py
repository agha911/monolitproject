import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from app.auth import require_telegram_user, validate_init_data

TOKEN = "123456789:test-only-token"


def signed(user_id=101, auth_date=None, **extra):
    data = {"user": json.dumps({"id": user_id, "first_name": "A + B %"}),
            "auth_date": str(int(time.time()) if auth_date is None else auth_date), **extra}
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    data["hash"] = hmac.new(secret, "\n".join(f"{k}={v}" for k, v in sorted(data.items())).encode(), hashlib.sha256).hexdigest()
    return urlencode(data)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    app = FastAPI(dependencies=[Depends(require_telegram_user)])

    @app.api_route("/api/example", methods=["GET", "POST"])
    @app.post("/api/task/daily")
    @app.post("/api/shop/tshirt/admin/activate")
    async def endpoint(request: Request):
        return {"id": request.state.telegram_user_id}

    return TestClient(app)


def test_valid_signature_and_percent_decoding():
    assert validate_init_data(signed(), bot_token=TOKEN) == 101


@pytest.mark.parametrize("data", ["user=%7B%22id%22%3A101%7D", {"user": {"id": 101}}, "", "hash=x&hash=y"])
def test_unsigned_or_malformed_rejected(data):
    with pytest.raises(Exception) as exc:
        validate_init_data(data, bot_token=TOKEN)
    assert exc.value.status_code == 401


def test_wrong_token_and_tampering():
    for raw, token in [(signed(), "wrong"), (signed().replace("101", "202"), TOKEN)]:
        with pytest.raises(Exception) as exc:
            validate_init_data(raw, bot_token=token)
        assert exc.value.status_code == 401


@pytest.mark.parametrize("offset", [-3601, 31])
def test_expired_and_future_credentials(offset):
    now = int(time.time())
    with pytest.raises(Exception) as exc:
        validate_init_data(signed(auth_date=now + offset), bot_token=TOKEN, now=now)
    assert exc.value.status_code == 401


def test_duplicate_fields_rejected():
    with pytest.raises(Exception) as exc:
        validate_init_data(signed() + "&user=other", bot_token=TOKEN)
    assert exc.value.status_code == 401


def test_get_header_auth(client):
    response = client.get("/api/example?telegram_id=101", headers={"X-Telegram-Init-Data": signed()})
    assert response.status_code == 200
    assert response.json() == {"id": 101}


def test_legacy_body_auth(client):
    assert client.post("/api/example", json={"init_data": signed(), "telegram_id": 101}).status_code == 200


def test_id_alone_is_not_authentication(client):
    assert client.post("/api/example", json={"telegram_id": 101}).status_code == 401


@pytest.mark.parametrize("where", ["query", "body", "header", "task"])
def test_other_user_cannot_be_impersonated(client, where):
    headers = {"X-Telegram-Init-Data": signed()}
    if where == "query":
        response = client.get("/api/example?telegram_id=202", headers=headers)
    elif where == "header":
        response = client.get("/api/example", headers={**headers, "X-Telegram-User-Id": "202"})
    elif where == "task":
        response = client.post("/api/task/daily", json={"user_id": 202}, headers=headers)
    else:
        response = client.post("/api/example", json={"telegram_id": 202}, headers=headers)
    assert response.status_code == 403


def test_conflicting_signed_body_rejected(client):
    response = client.post("/api/example", json={"init_data": signed(202)},
                           headers={"X-Telegram-Init-Data": signed(101)})
    assert response.status_code == 403


def test_expired_body_cannot_hide_behind_valid_header(client):
    response = client.post("/api/example", json={"init_data": signed(auth_date=1)},
                           headers={"X-Telegram-Init-Data": signed()})
    assert response.status_code == 401


def test_legacy_header_must_match_primary_header(client):
    response = client.get("/api/example", headers={"X-Telegram-Init-Data": signed(101),
                                                  "init-data": signed(202)})
    assert response.status_code == 403


def test_regular_user_cannot_toggle_shop(client, monkeypatch):
    monkeypatch.delenv("MONOLIT_ADMIN_KEY", raising=False)
    assert client.post("/api/shop/tshirt/admin/activate", json={},
                       headers={"X-Telegram-Init-Data": signed()}).status_code == 403
    monkeypatch.setenv("MONOLIT_ADMIN_KEY", "test-admin-key")
    assert client.post("/api/shop/tshirt/admin/activate", json={},
                       headers={"X-Telegram-Init-Data": signed(), "X-Admin-Key": "wrong"}).status_code == 403
    assert client.post("/api/shop/tshirt/admin/activate", json={},
                       headers={"X-Telegram-Init-Data": signed(), "X-Admin-Key": "test-admin-key"}).status_code == 200
