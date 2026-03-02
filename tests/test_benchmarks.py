"""
Performance benchmarks for CPU-bound code paths.

Run locally:
    uv run pytest tests/test_benchmarks.py -v --benchmark-sort=mean

These are excluded from CI — see .github/workflows/ci.yml.
"""

import json

import pytest

from app.cache.service import CacheService
from app.config import Settings
from app.weather.schema import WeatherRequest, WeatherResponse

# ---------------------------------------------------------------------------
# Fixture data — realistic 15-day forecast with hourly data
# Mirrors the default Visual Crossing response shape so timings are
# representative of real traffic.
# ---------------------------------------------------------------------------


def _make_hour(hour: int) -> dict:
    return {
        "datetime": f"{hour:02d}:00:00",
        "datetimeEpoch": 1704067200 + hour * 3600,
        "temp": 55.0 + hour * 0.5,
        "feelslike": 50.0,
        "humidity": 70.0,
        "dew": 45.0,
        "precip": 0.0,
        "precipprob": 10.0,
        "preciptype": None,
        "snow": 0.0,
        "snowdepth": 0.0,
        "windgust": 15.0,
        "windspeed": 10.0,
        "winddir": 180.0,
        "pressure": 1013.0,
        "cloudcover": 50.0,
        "visibility": 10.0,
        "solarradiation": 200.0,
        "solarenergy": 0.72,
        "uvindex": 3.0,
        "conditions": "Partly cloudy",
        "icon": "partly-cloudy-day",
        "source": "obs",
        "stations": ["EGLL"],
    }


def _make_day(day: int) -> dict:
    return {
        "datetime": f"2024-01-{day + 1:02d}",
        "datetimeEpoch": 1704067200 + day * 86400,
        "tempmax": 60.0,
        "tempmin": 45.0,
        "temp": 52.0,
        "feelslikemax": 56.0,
        "feelslikemin": 40.0,
        "feelslike": 48.0,
        "dew": 42.0,
        "humidity": 70.0,
        "precip": 0.05,
        "precipprob": 20.0,
        "precipcover": 10.0,
        "preciptype": None,
        "snow": 0.0,
        "snowdepth": 0.0,
        "windgust": 20.0,
        "windspeed": 12.0,
        "winddir": 220.0,
        "pressure": 1015.0,
        "cloudcover": 55.0,
        "visibility": 9.0,
        "uvindex": 3.0,
        "severerisk": 10.0,
        "sunrise": "07:58:00",
        "sunriseEpoch": 1704092280,
        "sunset": "16:02:00",
        "sunsetEpoch": 1704121320,
        "moonphase": 0.65,
        "conditions": "Partially cloudy",
        "description": "Partly cloudy throughout the day.",
        "icon": "partly-cloudy-day",
        "source": "comb",
        "stations": ["EGLL"],
        "hours": [_make_hour(h) for h in range(24)],
    }


RESPONSE_DICT: dict = {
    "queryCost": 1,
    "latitude": 51.506,
    "longitude": -0.127,
    "resolvedAddress": "London, England, United Kingdom",
    "address": "London,UK",
    "timezone": "Europe/London",
    "tzoffset": 0.0,
    "description": "Similar temperatures continuing with a chance of rain.",
    "days": [_make_day(i) for i in range(15)],
    "alerts": [],
    "currentConditions": {
        "datetime": "12:00:00",
        "datetimeEpoch": 1704110400,
        "temp": 54.5,
        "feelslike": 50.2,
        "humidity": 72.0,
        "dew": 46.0,
        "precip": 0.0,
        "precipprob": 0.0,
        "preciptype": None,
        "snow": 0.0,
        "snowdepth": 0.0,
        "windgust": 16.0,
        "windspeed": 9.0,
        "winddir": 200.0,
        "pressure": 1014.0,
        "cloudcover": 48.0,
        "visibility": 10.0,
        "solarradiation": 250.0,
        "solarenergy": 0.9,
        "uvindex": 2.0,
        "sunrise": "07:58:00",
        "sunriseEpoch": 1704092280,
        "sunset": "16:02:00",
        "sunsetEpoch": 1704121320,
        "moonphase": 0.65,
        "conditions": "Overcast",
        "icon": "cloudy",
        "source": "obs",
        "stations": ["EGLL"],
    },
    "stations": {
        "EGLL": {
            "name": "London Heathrow",
            "latitude": 51.477,
            "longitude": -0.461,
            "distance": 24.0,
            "usecount": 15,
            "id": "EGLL",
            "contribution": 1.0,
            "quality": 50,
        }
    },
}

# Pre-serialised for the JSON benchmarks — built once at module load.
RESPONSE_JSON: str = json.dumps(RESPONSE_DICT)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def weather_request() -> WeatherRequest:
    return WeatherRequest(location="London,UK", date1="2024-01-01", date2="2024-01-15")


@pytest.fixture(scope="module")
def cache_service() -> CacheService:
    # Only _create_key() is exercised — client is never called.
    settings = Settings(
        weather_api_key="dummy", redis_password="dummy", api_key="dummy"
    )
    return CacheService(settings, client=None)  # type: ignore[arg-type]


@pytest.fixture(scope="module")
def parsed_response() -> WeatherResponse:
    return WeatherResponse.model_validate(RESPONSE_DICT)


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------


def test_bench_cache_key_generation(benchmark, weather_request, cache_service):
    """MD5 hash of the serialised WeatherRequest (runs on every request)."""
    benchmark(cache_service._create_key, weather_request)


def test_bench_request_model_parsing(benchmark):
    """Pydantic validation of an incoming WeatherRequest."""
    benchmark(
        WeatherRequest, location="London,UK", date1="2024-01-01", date2="2024-01-15"
    )


def test_bench_response_validate_from_dict(benchmark):
    """Validate a full 15-day + hourly response dict (cache-miss path).

    Exercises 15 DailyWeather objects × 24 HourlyWeather objects each.
    This is the most expensive Pydantic path in the application.
    """
    benchmark(WeatherResponse.model_validate, RESPONSE_DICT)


def test_bench_response_validate_from_json(benchmark):
    """Validate from a JSON string (cache-hit deserialisation path).

    Combines JSON parsing + Pydantic validation in one call.
    Compare against test_bench_response_validate_from_dict to see the
    overhead of JSON parsing vs pure Pydantic validation.
    """
    benchmark(WeatherResponse.model_validate_json, RESPONSE_JSON)


def test_bench_response_serialize_to_json(benchmark, parsed_response):
    """model_dump_json() — cache-set serialisation path (optimised).

    Uses Pydantic's Rust-backed serialiser directly instead of the prior
    model_dump(mode="json") + json.dumps() two-step round-trip.
    Runs once per cache miss, after a successful upstream API call.
    """
    benchmark(parsed_response.model_dump_json)
