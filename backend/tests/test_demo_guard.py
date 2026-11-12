import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize("url", [
    "postgresql+asyncpg://user:password@production.invalid/monolit_demo",
    "postgresql+asyncpg://user:password@127.0.0.1/production",
    "postgresql+asyncpg://user:password@db/monolit_demo",
    "postgresql://user:password@127.0.0.1/monolit_demo",
])
def test_demo_refuses_production_configuration(url):
    result = subprocess.run([sys.executable, "-c", "import app.demo"],
                            env={**os.environ, "DATABASE_URL": url, "MONOLIT_DEMO_CONTAINER": "false"},
                            capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert "Demo requires a loopback database named monolit_demo" in result.stderr


def test_container_mode_still_refuses_arbitrary_remote_hosts():
    result = subprocess.run([sys.executable, "-c", "import app.demo"],
                            env={**os.environ, "MONOLIT_DEMO_CONTAINER": "true",
                                 "DATABASE_URL": "postgresql+asyncpg://user:password@production.invalid/monolit_demo"},
                            capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert "Demo requires a loopback database" in result.stderr


def test_container_mode_accepts_only_explicit_demo_service():
    result = subprocess.run([sys.executable, "-c", "import app.demo"],
                            env={**os.environ, "MONOLIT_DEMO_CONTAINER": "true",
                                 "DATABASE_URL": "postgresql+asyncpg://user:password@db/monolit_demo"},
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
