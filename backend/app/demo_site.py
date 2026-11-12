"""Packaged LOCAL demo. This entry point is not a public deployment configuration."""
import os
from pathlib import Path

from app.demo import app as api_app
from app.browser_site import create_browser_site

directory = os.getenv("FRONTEND_DIST", str(Path(__file__).resolve().parents[2] / "frontend" / "dist"))
app = create_browser_site(api_app, directory)
