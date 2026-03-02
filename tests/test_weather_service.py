"""
Unit tests for WeatherService.

These tests instantiate the real WeatherService with mocked httpx and
CacheService dependencies. No HTTP layer, no dependency_overrides — every
line of the service class is exercised directly.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from httpx import HTTPStatusError, RequestError, Response, Request as HttpxRequest
from fastapi import HTTPException

from app.weather.service import WeatherService
from app.weather.schema import WeatherRequest, WeatherResponse, IncludeOption
from app.config import Settings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def settings():
    return Settings(weather_api_key="dummy", redis_password="dummy", api_key="dummy")


@pytest.fixture
def mock_http():
    return AsyncMock()


@pytest.fixture
def mock_cache():
    return AsyncMock()


@pytest.fixture
def svc(mock_http, mock_cache, settings):
    return WeatherService(mock_http, mock_cache, settings)


# ---------------------------------------------------------------------------
# _build_url
# ---------------------------------------------------------------------------


def test_build_url_location_only(svc, settings):
    url = svc._build_url(WeatherRequest(location="London,UK"))
    assert url == f"{settings.weather_api_url}/London,UK"


def test_build_url_with_date1(svc, settings):
    url = svc._build_url(WeatherRequest(location="London", date1="2024-01-01"))
    assert url == f"{settings.weather_api_url}/London/2024-01-01"


def test_build_url_with_date1_and_date2(svc, settings):
    url = svc._build_url(
        WeatherRequest(location="London", date1="2024-01-01", date2="2024-01-07")
    )
    assert url == f"{settings.weather_api_url}/London/2024-01-01/2024-01-07"


# ---------------------------------------------------------------------------
# _build_params
# ---------------------------------------------------------------------------


def test_build_params_defaults(svc):
    params = svc._build_params(WeatherRequest(location="London"))
    assert params["unitGroup"] == "us"
    assert params["lang"] == "en"
    assert "include" not in params
    assert "elements" not in params


def test_build_params_with_include(svc):
    req = WeatherRequest(
        location="London", include=[IncludeOption.CURRENT, IncludeOption.DAYS]
    )
    params = svc._build_params(req)
    assert "current" in params["include"]
    assert "days" in params["include"]


def test_build_params_with_elements(svc):
    req = WeatherRequest(location="London", elements=["temp", "humidity"])
    params = svc._build_params(req)
    assert params["elements"] == "temp,humidity"


# ---------------------------------------------------------------------------
# get_weather — happy paths
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_get_weather_cache_hit(svc, mock_http, mock_cache):
    """Cache hit: returns the deserialised response; upstream API is never called."""
    mock_cache.get.return_value = WeatherResponse(address="London").model_dump_json()

    result = await svc.get_weather(WeatherRequest(location="London"))

    assert result.address == "London"
    mock_http.get.assert_not_called()


@pytest.mark.anyio
async def test_get_weather_cache_miss_calls_api_and_caches(svc, mock_http, mock_cache):
    """Cache miss: fetches from upstream, stores result, returns parsed response."""
    mock_cache.get.return_value = None
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"days": [], "alerts": [], "address": "London"}
    mock_http.get.return_value = mock_response

    result = await svc.get_weather(WeatherRequest(location="London"))

    assert result.address == "London"
    mock_http.get.assert_called_once()
    mock_cache.set.assert_called_once()


# ---------------------------------------------------------------------------
# get_weather — error paths
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_get_weather_http_status_error_propagates_status_code(
    svc, mock_http, mock_cache
):
    """Upstream 4xx/5xx is re-raised as HTTPException with the same status code."""
    mock_cache.get.return_value = None
    httpx_req = HttpxRequest("GET", "https://example.com")
    httpx_resp = Response(502, request=httpx_req)
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = HTTPStatusError(
        "Bad gateway", request=httpx_req, response=httpx_resp
    )
    mock_http.get.return_value = mock_response

    with pytest.raises(HTTPException) as exc_info:
        await svc.get_weather(WeatherRequest(location="London"))

    assert exc_info.value.status_code == 502


@pytest.mark.anyio
async def test_get_weather_request_error_raises_503(svc, mock_http, mock_cache):
    """Network/transport errors are surfaced as 503 Service Unavailable."""
    mock_cache.get.return_value = None
    mock_http.get.side_effect = RequestError("connection timed out")

    with pytest.raises(HTTPException) as exc_info:
        await svc.get_weather(WeatherRequest(location="London"))

    assert exc_info.value.status_code == 503
