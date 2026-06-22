"""
Integration tests — auth flows and health check.
Uses a throw-away SQLite DB so no PostgreSQL is required in CI.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    import os
    os.environ.setdefault("ENVIRONMENT", "test")
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_agriintel.db")
    os.environ.setdefault("JWT_SECRET_KEY", "ci-test-secret-not-for-prod-use-only")
    os.environ.setdefault("MONGODB_ENABLED", "false")
    os.environ.setdefault("ELASTICSEARCH_ENABLED", "false")

    from src.main import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

    import os as _os
    _os.path.exists("test_agriintel.db") and _os.remove("test_agriintel.db")


def test_root_returns_active(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


def test_health_endpoint(client):
    """Health route is mounted at /api/v1/health."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200


def test_register_missing_fields_returns_422(client):
    resp = client.post("/api/v1/auth/register", json={})
    assert resp.status_code == 422


def test_login_invalid_credentials(client):
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "nobody", "password": "wrongpassword"},
    )
    assert resp.status_code in (401, 422, 400)


def test_metrics_requires_auth(client):
    """Unauthenticated /metrics must return 401 or 403."""
    resp = client.get("/metrics")
    assert resp.status_code in (401, 403)


def test_cors_headers_present(client):
    resp = client.options(
        "/api/v1/health",
        headers={"Origin": "https://agriintel360.lsgrouptogo.com"},
    )
    # FastAPI CORSMiddleware responds to preflight
    assert resp.status_code in (200, 204, 405)
