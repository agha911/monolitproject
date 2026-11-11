from contextlib import asynccontextmanager

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.browser_site import create_browser_site


def test_browser_site_keeps_spa_api_assets_and_lifespan_separate(tmp_path):
    (tmp_path / "index.html").write_text("<h1>Monolit demo</h1>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('demo');", encoding="utf-8")
    state = {"started": False}

    @asynccontextmanager
    async def lifespan(app):
        state["started"] = True
        yield
        state["started"] = False

    async def health(request):
        return JSONResponse({"ready": state["started"]})

    api = Starlette(routes=[Route("/", health), Route("/api/status", health)], lifespan=lifespan)
    with TestClient(create_browser_site(api, tmp_path)) as client:
        for path in ("/", "/tasks", "/pvp", "/playground"):
            response = client.get(path)
            assert response.status_code == 200 and "Monolit demo" in response.text
        assert client.get("/assets/app.js").status_code == 200
        assert client.get("/health").json() == {"ready": True}
        assert client.get("/api/status").json() == {"ready": True}
        for path in ("/api/missing", "/demo/missing", "/assets/missing.js", "/missing", "/.env"):
            assert client.get(path).status_code == 404
        assert client.post("/tasks").status_code == 405
    assert state["started"] is False


def test_browser_site_requires_a_compiled_frontend(tmp_path):
    with pytest.raises(RuntimeError, match="Build the demo frontend"):
        create_browser_site(Starlette(), tmp_path)
