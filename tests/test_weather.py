import pytest
from app.config import get_settings
from app.weather.schema import WeatherResponse
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
    mock_weather_service.get_weather.side_effect = HTTPException(status_code=503, detail="Could not reach weather service")
    response = client.get("/v1/weather?location=London,UK")
    assert response.status_code == 503