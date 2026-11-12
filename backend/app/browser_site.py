"""Serve a compiled browser demo and its API from one origin."""
from pathlib import Path

from starlette.applications import Starlette
from starlette.responses import FileResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles


def create_browser_site(api_app, directory):
    directory = Path(directory).resolve()
    index = directory / "index.html"
    if not index.is_file():
        raise RuntimeError("Build the demo frontend before starting the browser site")

    async def page(request):
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    frontend = Starlette(routes=[
        *(Route(path, page) for path in ("/", "/tasks", "/pvp", "/playground")),
        Mount("/", app=StaticFiles(directory=directory)),
    ])

    async def site(scope, receive, send):
        # Forward lifespan to the API: schema initialization, seeding and shutdown.
        if scope["type"] != "http":
            await api_app(scope, receive, send)
            return
        path = scope["path"]
        if path == "/health":
            scope = {**scope, "path": "/", "raw_path": b"/"}
            await api_app(scope, receive, send)
        elif path == "/api" or path.startswith("/api/") or path == "/demo" or path.startswith("/demo/"):
            await api_app(scope, receive, send)
        else:
            await frontend(scope, receive, send)

    return site
