"""Smoke test for the dedicated local package, using Python's standard library."""
import json
import urllib.request

BASE = "http://127.0.0.1:8080"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=10) as response:
        return response.read().decode()


assert '<div id="root">' in get("/")
assert '<div id="root">' in get("/pvp")
get("/health")
session = json.loads(get("/demo/session"))
request = urllib.request.Request(
    BASE + "/api/game/progress",
    data=json.dumps({"init_data": session["init_data"]}).encode(),
    headers={"Content-Type": "application/json", "X-Telegram-Init-Data": session["init_data"]},
)
with urllib.request.urlopen(request, timeout=10) as response:
    progress = json.load(response)
assert isinstance(progress["total_xp"], int)
assert progress["max_energy"] >= 1000
print("Packaged demo: frontend, SPA route, health, session and authenticated progress passed.")
