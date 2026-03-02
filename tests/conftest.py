from pytest import fixture
from starlette.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from app.main import app
from app.auth import verify_api_key
from app.rate_limit import check_rate_limit
from app.database import get_session
from unittest.mock import AsyncMock, MagicMock
from app.cache.service import get_cache_service
from app.weather.service import get_weather_service
from app.config import Settings


@fixture
def settings():
    return Settings(weather_api_key="dummy", redis_password="dummy", api_key="dummy")


@fixture
def anyio_backend():
    return "asyncio"


def make_pipeline_ctx(execute_results):
    """Async context manager mock that returns a pipeline yielding execute_results."""
    pipe = MagicMock()
    pipe.execute = AsyncMock(return_value=execute_results)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=pipe)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


@fixture
def client():
    app.dependency_overrides[verify_api_key] = lambda: None
    app.dependency_overrides[check_rate_limit] = lambda: None
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@fixture
def raw_client():
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@fixture
def mock_weather_service():
    service = AsyncMock()
    app.dependency_overrides[get_weather_service] = lambda: service
    yield service


@fixture
def mock_cache_service():
    service = AsyncMock()
    app.dependency_overrides[get_cache_service] = lambda: service
    yield service


@fixture
def rate_limit_client():
    mock_redis = AsyncMock()
    app.dependency_overrides[verify_api_key] = lambda: None
    with TestClient(app, headers={"X-API-Key": "test-key"}) as c:
        app.state.redis_client = mock_redis  # override after lifespan runs
        yield c, mock_redis
    app.dependency_overrides.clear()


@fixture
def health_client():
    mock_redis = AsyncMock()
    mock_http_client = AsyncMock()
    app.dependency_overrides[verify_api_key] = lambda: None
    app.dependency_overrides[check_rate_limit] = lambda: None
    with TestClient(app, headers={"X-API-Key": "test-key"}) as c:
        app.state.redis_client = mock_redis
        app.state.http_client = mock_http_client
        yield c, mock_redis, mock_http_client
    app.dependency_overrides.clear()


@fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override
    yield factory
    app.dependency_overrides.pop(get_session, None)
    await engine.dispose()


@fixture
async def history_client(db_session):
    app.dependency_overrides[verify_api_key] = lambda: None
    app.dependency_overrides[check_rate_limit] = lambda: None
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-API-Key": "test-key"},
    ) as c:
        yield c
    app.dependency_overrides.pop(verify_api_key, None)
    app.dependency_overrides.pop(check_rate_limit, None)
