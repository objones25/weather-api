import pytest
from pydantic import ValidationError
from unittest.mock import AsyncMock, patch
from app.config import get_settings
from app.weather.schema import (
    BatchWeatherItem,
    BatchWeatherResponse,
    WeatherRequest,
    WeatherResponse,
)
from fastapi import HTTPException


settings = get_settings()


def test_get_weather_success(client, mock_weather_service):
    mock_weather_service.get_weather.return_value = WeatherResponse()
    response = client.get("/v1/weather?location=London,UK")
    assert response.status_code == 200


def test_get_weather_missing_location(client, mock_weather_service):
    response = client.get("/v1/weather")
    assert response.status_code == 422


def test_get_weather_upstream_error(client, mock_weather_service):
    mock_weather_service.get_weather.side_effect = HTTPException(
        status_code=503, detail="Could not reach weather service"
    )
    response = client.get("/v1/weather?location=London,UK")
    assert response.status_code == 503


# --- WeatherRequest validator unit tests ---
# These test Pydantic validators directly rather than through HTTP.
# FastAPI catches missing required fields (422) at the parameter level, but
# field_validator / model_validator errors raised inside Depends() model
# construction propagate as ValidationError before FastAPI can convert them.


def test_elements_validator_accepts_none():
    """Explicitly passing elements=None hits the early-return branch (line 175)."""
    req = WeatherRequest(location="London", elements=None)
    assert req.elements is None


def test_elements_validator_rejects_unknown():
    with pytest.raises(ValidationError, match="not a recognised element"):
        WeatherRequest(location="London", elements=["not_a_real_element"])


def test_location_validator_rejects_whitespace():
    with pytest.raises(ValidationError, match="location cannot be empty"):
        WeatherRequest(location="   ")


def test_date2_without_date1_is_rejected():
    with pytest.raises(ValidationError, match="date2 requires date1"):
        WeatherRequest(location="London", date2="2024-01-07")


# ---------------------------------------------------------------------------
# POST /v1/weather/batch
# ---------------------------------------------------------------------------


def test_post_weather_batch_success(client, mock_weather_service):
    mock_weather_service.get_weather_batch.return_value = BatchWeatherResponse(
        results=[
            BatchWeatherItem(
                location="London,UK",
                status="ok",
                result=WeatherResponse(address="London,UK"),
            ),
            BatchWeatherItem(
                location="Paris,FR",
                status="ok",
                result=WeatherResponse(address="Paris,FR"),
            ),
        ]
    )
    with patch("app.weather.routes.check_batch_rate_limit", new_callable=AsyncMock):
        response = client.post(
            "/v1/weather/batch",
            json={"locations": [{"location": "London,UK"}, {"location": "Paris,FR"}]},
        )
    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 2
    assert all(r["status"] == "ok" for r in data["results"])


def test_post_weather_batch_partial_failure(client, mock_weather_service):
    mock_weather_service.get_weather_batch.return_value = BatchWeatherResponse(
        results=[
            BatchWeatherItem(
                location="London,UK",
                status="ok",
                result=WeatherResponse(address="London,UK"),
            ),
            BatchWeatherItem(
                location="BadCity", status="error", error="400: Bad location"
            ),
        ]
    )
    with patch("app.weather.routes.check_batch_rate_limit", new_callable=AsyncMock):
        response = client.post(
            "/v1/weather/batch",
            json={"locations": [{"location": "London,UK"}, {"location": "BadCity"}]},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["results"][0]["status"] == "ok"
    assert data["results"][1]["status"] == "error"
    assert data["results"][1]["error"] == "400: Bad location"


def test_post_weather_batch_empty_list(client):
    response = client.post("/v1/weather/batch", json={"locations": []})
    assert response.status_code == 422


def test_post_weather_batch_exceeds_max_size(client):
    locations = [{"location": f"City{i}"} for i in range(11)]
    response = client.post("/v1/weather/batch", json={"locations": locations})
    assert response.status_code == 422


def test_post_weather_batch_logs_each_location(client, mock_weather_service):
    """Background task is added once per location."""
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
    with (
        patch("app.weather.routes.check_batch_rate_limit", new_callable=AsyncMock),
        patch("app.weather.routes._log_request") as mock_log,
    ):
        response = client.post(
            "/v1/weather/batch",
            json={"locations": [{"location": "London,UK"}, {"location": "Paris,FR"}]},
        )
    assert response.status_code == 200
    assert mock_log.call_count == 2
