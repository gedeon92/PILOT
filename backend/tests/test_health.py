from fastapi.testclient import TestClient

from pilot_api import db
from pilot_api.config import get_settings
from pilot_api.main import app


def _reset_caches() -> None:
    get_settings.cache_clear()
    db.get_engine.cache_clear()


def test_health_without_database(monkeypatch):
    # Une variable vide l'emporte sur un éventuel fichier .env local.
    monkeypatch.setenv("DATABASE_URL", "")
    _reset_caches()

    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "not_configured"
    _reset_caches()


def test_health_with_unreachable_database(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://pilot:secret@127.0.0.1:1/pilot")
    _reset_caches()

    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json()["database"] == "unavailable"
    _reset_caches()


def test_neon_url_is_converted_for_psycopg():
    assert db.to_sqlalchemy_url("postgresql://u:p@host/db?sslmode=require") == (
        "postgresql+psycopg://u:p@host/db?sslmode=require"
    )
    assert db.to_sqlalchemy_url("postgres://u:p@host/db") == "postgresql+psycopg://u:p@host/db"
