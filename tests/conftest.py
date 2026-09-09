"""Tests cannot open the user's DB or make real HTTP requests."""
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_bootstrap = tempfile.TemporaryDirectory(prefix="rental-pytest-")
os.environ["DB_PATH"] = str(Path(_bootstrap.name) / "bootstrap.db")
os.environ["ADMIN_TOKEN"] = ""
os.environ["NAVITIME_CLIENT_KEY"] = ""
os.environ["REINFOLIB_API_KEY"] = ""


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    import requests
    import config
    import db_helper
    from scripts.init_db import init_db
    path = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", path)
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(db_helper, "DB_PATH", path)
    for module_name in ("scripts.init_db", "scripts.seed_regions", "scripts.run_scrape",
                        "scripts.fetch_public_data", "scripts.recalculate_scores"):
        module = sys.modules.get(module_name)
        if module and hasattr(module, "DB_PATH"):
            monkeypatch.setattr(module, "DB_PATH", path)
    init_db(path)

    def no_network(*args, **kwargs):
        raise AssertionError("Tests must mock external HTTP requests")
    monkeypatch.setattr(requests.sessions.Session, "request", no_network)
    yield path


@pytest.fixture
def client():
    from app import app
    app.config.update(TESTING=True)
    with app.test_client() as client:
        yield client


def pytest_unconfigure(config):
    _bootstrap.cleanup()
