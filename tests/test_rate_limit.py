from unittest.mock import MagicMock
from app.weather.schema import BatchWeatherItem, BatchWeatherResponse, WeatherResponse
from app.config import get_settings
from tests.conftest import make_pipeline_ctx

settings = get_settings()


def test_under_limit(rate_limit_client, mock_weather_service):
    client, mock_redis = rate_limit_client
    # Read pipeline: count=0, no oldest entry. Write pipeline: success.
    mock_redis.pipeline = MagicMock(
        side_effect=[
            make_pipeline_ctx([None, 0, []]),
            make_pipeline_ctx([None, None]),
        ]
    )
    mock_weather_service.get_weather.return_value = WeatherResponse()
    response = client.get("/v1/weather?location=London,UK")
    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == "60"
    assert response.headers["X-RateLimit-Remaining"] == "60"
    assert "X-RateLimit-Reset" in response.headers


def test_at_limit(rate_limit_client):
    client, mock_redis = rate_limit_client
    # Read pipeline only — count=60 triggers 429 before write pipeline runs.
    mock_redis.pipeline = MagicMock(return_value=make_pipeline_ctx([None, 60, []]))
    response = client.get("/v1/weather?location=London,UK")
    assert response.status_code == 429
    assert response.json()["detail"] == "Rate limit exceeded"
    assert "Retry-After" in response.headers
    assert response.headers["X-RateLimit-Remaining"] == "0"


# ---------------------------------------------------------------------------
# check_batch_rate_limit — tested via POST /v1/weather/batch
# Pipeline order per request:
#   1. check_rate_limit read  (global dep): [zremrangebyscore=None, zcard=count, zrange=oldest]
#   2. check_rate_limit write (global dep): [zadd=None, expire=None]
#   3. check_batch_rate_limit read:         [zremrangebyscore=None, zcard=count, zrange=oldest]
#   4. check_batch_rate_limit write (n+1):  [zadd=None]*n + [expire=None]   (only if not rejected)
# ---------------------------------------------------------------------------


def test_batch_under_limit(rate_limit_client, mock_weather_service):
    """Batch of 2 with plenty of capacity → 200, headers reflect batch limiter values."""
    client, mock_redis = rate_limit_client
    mock_weather_service.get_weather_batch.return_value = BatchWeatherResponse(
        results=[
            BatchWeatherItem(
                location="London,UK", status="ok", result=WeatherResponse()
            ),
            BatchWeatherItem(
                location="Paris,FR", status="ok", result=WeatherResponse()
            ),
        ]
    )
    mock_redis.pipeline = MagicMock(
        side_effect=[
            make_pipeline_ctx([None, 0, []]),  # check_rate_limit: read (0 existing)
            make_pipeline_ctx([None, None]),  # check_rate_limit: write
            make_pipeline_ctx(
                [None, 1, []]
            ),  # check_batch_rate_limit: read (1 after global)
            make_pipeline_ctx(
                [None, None, None]
            ),  # check_batch_rate_limit: write (zadd*2 + expire)
        ]
    )
    response = client.post(
        "/v1/weather/batch",
        json={"locations": [{"location": "London,UK"}, {"location": "Paris,FR"}]},
    )
    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == "60"
    assert response.headers["X-RateLimit-Remaining"] == "59"  # max(60-1, 0)
    assert "X-RateLimit-Reset" in response.headers


def test_batch_exceeds_limit(rate_limit_client):
    """Batch of 3 when 59 units are consumed → 429 with batch-specific detail."""
    client, mock_redis = rate_limit_client
    # 58 existing → global dep (count=58 < 60) passes and adds 1.
    # Batch read sees count=59. 59 + 3 = 62 > 60 → rejected.
    mock_redis.pipeline = MagicMock(
        side_effect=[
            make_pipeline_ctx(
                [None, 58, [("uid", 1700000000.0)]]
            ),  # check_rate_limit: read
            make_pipeline_ctx([None, None]),  # check_rate_limit: write
            make_pipeline_ctx(
                [None, 59, [("uid", 1700000000.0)]]
            ),  # check_batch_rate_limit: read
            # No write pipeline — rejected before second pipeline executes
        ]
    )
    locations = [{"location": f"City{i}"} for i in range(3)]
    response = client.post("/v1/weather/batch", json={"locations": locations})
    assert response.status_code == 429
    assert "batch of 3 requires 3 units" in response.json()["detail"]
    assert "Retry-After" in response.headers
    assert response.headers["X-RateLimit-Remaining"] == "0"


def test_batch_with_oldest_entry_sets_reset_time(
    rate_limit_client, mock_weather_service
):
    """When oldest entry exists, reset time is derived from its timestamp."""
    client, mock_redis = rate_limit_client
    mock_weather_service.get_weather_batch.return_value = BatchWeatherResponse(
        results=[
            BatchWeatherItem(
                location="London,UK", status="ok", result=WeatherResponse()
            )
        ]
    )
    oldest_ts = 1700000000.0
    mock_redis.pipeline = MagicMock(
        side_effect=[
            make_pipeline_ctx(
                [None, 0, [("uid", oldest_ts)]]
            ),  # check_rate_limit: read
            make_pipeline_ctx([None, None]),  # check_rate_limit: write
            make_pipeline_ctx(
                [None, 1, [("uid", oldest_ts)]]
            ),  # check_batch_rate_limit: read
            make_pipeline_ctx(
                [None, None]
            ),  # check_batch_rate_limit: write (zadd*1 + expire)
        ]
    )
    response = client.post(
        "/v1/weather/batch",
        json={"locations": [{"location": "London,UK"}]},
    )
    assert response.status_code == 200
    # Reset time = oldest_ts + window (60s) = 1700000060
    assert response.headers["X-RateLimit-Reset"] == str(
        int(oldest_ts + settings.rate_limit_window)
    )
