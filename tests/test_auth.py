"""
Tests for authentication endpoints
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from config.config import get_settings
from config.database import get_db, Base
from src.main import app

settings = get_settings()

TEST_DATABASE_URL = settings.DATABASE_URL.replace(
    "agriintel360", "agriintel360_test"
).replace("postgresql://", "postgresql+asyncpg://")

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(engine):
    session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_maker() as session:
        yield session


@pytest.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


REGISTER_PAYLOAD = {
    "email": "testuser@example.com",
    "username": "testuser",
    "full_name": "Test User",
    "password": "StrongPass1",
    "language": "fr",
    "timezone": "Africa/Dakar",
}


@pytest.mark.asyncio
async def test_health_check(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_register_user(client):
    response = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == REGISTER_PAYLOAD["email"]
    assert data["username"] == REGISTER_PAYLOAD["username"]
    assert "id" in data
    assert "password" not in data


@pytest.mark.asyncio
async def test_duplicate_registration_returns_400(client):
    await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    response = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_login_success(client):
    await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    response = await client.post("/api/v1/auth/login", json={
        "username": REGISTER_PAYLOAD["username"],
        "password": REGISTER_PAYLOAD["password"],
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == REGISTER_PAYLOAD["email"]


@pytest.mark.asyncio
async def test_login_invalid_credentials_returns_401(client):
    await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    response = await client.post("/api/v1/auth/login", json={
        "username": REGISTER_PAYLOAD["username"],
        "password": "WrongPass1",
    })
    assert response.status_code == 401
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_login_nonexistent_user_returns_401(client):
    response = await client.post("/api/v1/auth/login", json={
        "username": "nobody",
        "password": "SomePass1",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(client):
    await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    login_resp = await client.post("/api/v1/auth/login", json={
        "username": REGISTER_PAYLOAD["username"],
        "password": REGISTER_PAYLOAD["password"],
    })
    login_data = login_resp.json()
    refresh_token = login_data["refresh_token"]

    response = await client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": f"Bearer {refresh_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["expires_in"] > 0


@pytest.mark.asyncio
async def test_refresh_with_invalid_token_returns_401(client):
    response = await client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": "Bearer invalid_token_here"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_register_missing_fields_returns_422(client):
    response = await client.post("/api/v1/auth/register", json={
        "email": "bad@example.com",
    })
    assert response.status_code == 422
