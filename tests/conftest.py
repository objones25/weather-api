from pytest import fixture
from starlette.testclient import TestClient
from app.main import app
from app.auth import verify_api_key
from app.rate_limit import check_rate_limit
from unittest.mock import AsyncMock
from app.cache.service import get_cache_service
from app.weather.service import get_weather_service

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