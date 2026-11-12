"""Two real HTTP visitors must have independent progress in the packaged candidate."""
import http.cookiejar
import json
import os
import urllib.error
import urllib.request

BASE = os.environ.get("DEMO_PUBLIC_ORIGIN", "http://127.0.0.1:8080")


def visitor():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def request(browser, path, body=None, credential=None):
    headers = {"Origin": BASE, "Content-Type": "application/json"}
    if credential:
        headers["X-Telegram-Init-Data"] = credential
    call = urllib.request.Request(BASE + path, headers=headers,
        data=json.dumps(body).encode() if body is not None else None)
    return browser.open(call, timeout=20)


first, second = visitor(), visitor()
with request(first, "/demo/session", {}) as response:
    one = json.load(response)["init_data"]
with request(second, "/demo/session", {}) as response:
    two = json.load(response)["init_data"]
assert one != two
with request(first, "/api/game/clicks/flush", {"init_data": one, "delta_clicks": 10,
    "client_seq": 1, "session_id": "packaged-visitors"}, one) as response:
    assert json.load(response)["total_xp"] == 12010
with request(second, "/api/game/progress", {"init_data": two}, two) as response:
    assert json.load(response)["total_xp"] == 12000
with request(second, "/api/pvp/challenge/start", {"telegram_id": 900000001}, two) as response:
    attempt = json.load(response)["attempt_id"]
with request(second, "/api/pvp/challenge/finish", {"telegram_id": 900000001,
    "attempt_id": attempt, "my_clicks": 1}, two) as response:
    assert json.load(response)["is_win"] is False
for browser, path, body, credential, expected in (
    (second, "/api/game/leaderboard", None, one, 401),
    (visitor(), "/api/game/leaderboard", None, one, 401),
    (first, "/api/pvp/admin/reset-weekly", {}, one, 404),
    (first, "/api/partner/redeem", {}, one, 404),
):
    try:
        request(browser, path, body, credential)
        raise AssertionError(f"Unexpected access: {path}")
    except urllib.error.HTTPError as error:
        assert error.code == expected, (path, error.code)
with urllib.request.urlopen(BASE, timeout=10) as response:
    assert response.headers["X-Frame-Options"] == "DENY"
print("Visitor demo: separate progress, challenge PvP, bound credentials, blocked privileged routes and browser headers passed.")
