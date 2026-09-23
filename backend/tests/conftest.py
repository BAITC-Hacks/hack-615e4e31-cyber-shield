"""Each integration test owns a temporary database; real demo data is untouched."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture(autouse=True)
def offline_environment(monkeypatch):
    # Tests must never use the developer's .env or make paid provider calls.
    monkeypatch.setenv("ALEM_LOAD_ENV", "0")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.delenv("OPENAI_RATING_MODEL", raising=False)


@pytest.fixture
def app_db_path(tmp_path, monkeypatch):
    db_path = tmp_path / "test-hackalem.sqlite3"
    monkeypatch.setenv("APP_DB_PATH", str(db_path))
    return db_path


@pytest.fixture
def app_factory(app_db_path):
    # Import after setting APP_DB_PATH, including for any module-level app object.
    from app.main import create_app

    return lambda: create_app(db_path=app_db_path)


@pytest.fixture
def client(app_factory):
    with TestClient(app_factory()) as test_client:
        yield test_client
