"""
Unit tests for CacheService.

These tests instantiate the real CacheService with a mocked Redis client.
No HTTP layer, no dependency_overrides — every method is exercised directly.
"""

import json
import pytest
from unittest.mock import AsyncMock

from app.cache.service import CacheService
from app.weather.schema import WeatherRequest, WeatherResponse
from app.config import Settings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def settings():
    return Settings(weather_api_key="dummy", redis_password="dummy", api_key="dummy")


@pytest.fixture
def redis():
    return AsyncMock()


@pytest.fixture
def svc(settings, redis):
    return CacheService(settings, redis)


# ---------------------------------------------------------------------------
# _create_key
# ---------------------------------------------------------------------------


def test_create_key_is_deterministic(svc):
    req = WeatherRequest(location="London,UK")
    assert svc._create_key(req) == svc._create_key(req)


def test_create_key_differs_by_location(svc):
    assert svc._create_key(WeatherRequest(location="London")) != svc._create_key(
        WeatherRequest(location="Paris")
    )


def test_create_key_differs_by_params(svc):
    base = WeatherRequest(location="London")
    with_date = WeatherRequest(location="London", date1="2024-01-01")
    assert svc._create_key(base) != svc._create_key(with_date)


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_get_returns_cached_value_on_hit(svc, redis):
    redis.get.return_value = '{"days": []}'
    result = await svc.get(WeatherRequest(location="London"))
    assert result == '{"days": []}'


@pytest.mark.anyio
async def test_get_returns_none_on_miss(svc, redis):
    redis.get.return_value = None
    result = await svc.get(WeatherRequest(location="London"))
    assert result is None


# ---------------------------------------------------------------------------
# set
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_set_stores_valid_json(svc, redis):
    req = WeatherRequest(location="London")
    resp = WeatherResponse(address="London")

    await svc.set(req, resp)

    redis.set.assert_called_once()
    _, stored_value = redis.set.call_args.args
    parsed = json.loads(stored_value)
    assert parsed["address"] == "London"


@pytest.mark.anyio
async def test_set_uses_configured_ttl(svc, redis, settings):
    await svc.set(WeatherRequest(location="London"), WeatherResponse())
    assert redis.set.call_args.kwargs["ex"] == settings.cache_ttl


@pytest.mark.anyio
async def test_set_key_matches_get_key(svc, redis):
    """The key used by set() is the same MD5 that get() would look up."""
    req = WeatherRequest(location="London")
    expected_key = svc._create_key(req)

    await svc.set(req, WeatherResponse())

    stored_key, _ = redis.set.call_args.args
    assert stored_key == expected_key


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_delete_calls_redis_with_correct_key(svc, redis):
    req = WeatherRequest(location="London")
    expected_key = svc._create_key(req)

    await svc.delete(req)

    redis.delete.assert_called_once_with(expected_key)
