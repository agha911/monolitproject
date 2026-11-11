import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize("url", [
    "postgresql+asyncpg://user:password@production.invalid/monolit_demo",
    "postgresql+asyncpg://user:password@127.0.0.1/production",
])
def test_demo_refuses_production_configuration(url):
    result = subprocess.run([sys.executable, "-c", "import app.demo"],
                            env={**os.environ, "DATABASE_URL": url}, capture_output=True, text=True)
    assert result.returncode != 0
    assert "Demo requires a loopback database named monolit_demo" in result.stderr
