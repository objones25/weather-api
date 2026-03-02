"""
Unit tests for CacheService.

These tests instantiate the real CacheService with a mocked Redis client.
No HTTP layer, no dependency_overrides — every method is exercised directly.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.cache.service import CacheService, CacheResult
from app.weather.schema import WeatherRequest, WeatherResponse


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def redis():
    mock = MagicMock()
    # Default pipeline: miss (value=None, ttl=-2)
    _set_pipeline(mock, value=None, ttl=-2)
    # set/delete are async in the real client
    mock.set = AsyncMock()
    mock.delete = AsyncMock()
    return mock


@pytest.fixture
def svc(settings, redis):
    return CacheService(settings, redis)


def _set_pipeline(redis_mock, *, value, ttl):
    """Configure a sync pipeline() that returns an async context manager.

    redis.asyncio.Redis.pipeline() is a sync method — it must be a MagicMock,
    not an AsyncMock, or calling it returns a coroutine instead of the pipeline
    object and the `async with` protocol breaks.
    """
    pipe = MagicMock()
    pipe.get = MagicMock()
    pipe.ttl = MagicMock()
    pipe.execute = AsyncMock(return_value=[value, ttl])
    pipe.__aenter__ = AsyncMock(return_value=pipe)
    pipe.__aexit__ = AsyncMock(return_value=False)
    redis_mock.pipeline = MagicMock(return_value=pipe)


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
# get — hit / miss / needs_refresh
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_get_returns_none_on_miss(svc, redis):
    # Default fixture is already a miss
    result = await svc.get(WeatherRequest(location="London"))
    assert isinstance(result, CacheResult)
    assert result.value is None
    assert result.needs_refresh is False


@pytest.mark.anyio
async def test_get_returns_value_on_hit(svc, redis):
    _set_pipeline(redis, value='{"days": []}', ttl=40000)
    result = await svc.get(WeatherRequest(location="London"))
    assert result.value == '{"days": []}'
    assert result.needs_refresh is False


@pytest.mark.anyio
async def test_get_needs_refresh_when_ttl_below_threshold(svc, redis, settings):
    # warm_threshold=0.2, cache_ttl=43200 → threshold = 8640s
    # ttl=1000 is below threshold → needs_refresh=True
    _set_pipeline(redis, value='{"days": []}', ttl=1000)
    result = await svc.get(WeatherRequest(location="London"))
    assert result.value is not None
    assert result.needs_refresh is True


@pytest.mark.anyio
async def test_get_no_refresh_when_ttl_above_threshold(svc, redis):
    # ttl=40000 is well above the 8640s threshold
    _set_pipeline(redis, value='{"days": []}', ttl=40000)
    result = await svc.get(WeatherRequest(location="London"))
    assert result.needs_refresh is False


@pytest.mark.anyio
async def test_get_no_refresh_when_no_expiry(svc, redis):
    # ttl=-1 means key has no TTL set — should not trigger warming
    _set_pipeline(redis, value='{"days": []}', ttl=-1)
    result = await svc.get(WeatherRequest(location="London"))
    assert result.needs_refresh is False


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


# ---------------------------------------------------------------------------
# _normalize_location
# ---------------------------------------------------------------------------


def test_normalize_location_lowercases_and_strips(svc):
    assert svc._normalize_location("  NEW YORK  ") == "new york"


def test_normalize_location_collapses_whitespace(svc):
    assert svc._normalize_location("new  york") == "new york"


def test_normalize_location_normalizes_commas(svc):
    assert svc._normalize_location("new york , ny") == "new york, ny"


# ---------------------------------------------------------------------------
# _create_key — normalization
# ---------------------------------------------------------------------------


def test_create_key_case_insensitive(svc):
    assert svc._create_key(WeatherRequest(location="London,UK")) == svc._create_key(
        WeatherRequest(location="LONDON,UK")
    )


def test_create_key_whitespace_insensitive(svc):
    assert svc._create_key(WeatherRequest(location="New York")) == svc._create_key(
        WeatherRequest(location="  new york  ")
    )


# ---------------------------------------------------------------------------
# set — resolvedAddress alias
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_set_writes_resolved_address_alias(svc, redis):
    """When resolvedAddress differs from the request location, a second Redis
    entry is written so future queries for the canonical form hit the cache."""
    req = WeatherRequest(location="nyc")
    resp = WeatherResponse(resolvedAddress="New York, NY, United States")

    await svc.set(req, resp)

    assert redis.set.call_count == 2


@pytest.mark.anyio
async def test_set_no_alias_when_resolved_matches_normalized(svc, redis):
    """If the resolvedAddress normalises to the same key, only one write occurs."""
    req = WeatherRequest(location="London, UK")
    resp = WeatherResponse(resolvedAddress="london, uk")

    await svc.set(req, resp)

    assert redis.set.call_count == 1


@pytest.mark.anyio
async def test_set_no_alias_when_no_resolved_address(svc, redis):
    """No alias write when the response carries no resolvedAddress."""
    await svc.set(WeatherRequest(location="London"), WeatherResponse())

    assert redis.set.call_count == 1
