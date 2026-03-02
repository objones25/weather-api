from unittest.mock import MagicMock
from app.weather.schema import WeatherResponse
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
