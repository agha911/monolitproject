"""Smoke test against the real app, with no network or database access."""
import importlib
import pkgutil
import socket

from fastapi.testclient import TestClient


def test_local_startup_does_not_connect_or_start_workers(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@127.0.0.1:5432/monolit_test")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456789:test-only-token")
    for name in ("ENABLE_BOT_POLLING", "ENABLE_NOTIFICATIONS", "ENABLE_SEASON_WORKER",
                 "ENABLE_HISTORICAL_FINALIZER", "ALLOW_TELEGRAM_LOOKUPS"):
        monkeypatch.delenv(name, raising=False)

    original_connect = socket.socket.connect

    def deny_connection(sock, address):
        # Windows asyncio creates a loopback socketpair for its event loop.
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"} and address[1] != 5432:
            return original_connect(sock, address)
        raise AssertionError("Local startup must not connect to external systems")

    monkeypatch.setattr(socket.socket, "connect", deny_connection)
    from app.main import app, _background_tasks
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/game/leaderboard").status_code == 401
        assert _background_tasks == []
    assert _background_tasks == []

    from app import models
    for module in pkgutil.iter_modules(models.__path__):
        importlib.import_module(f"app.models.{module.name}")
    from sqlalchemy.orm import configure_mappers
    configure_mappers()
