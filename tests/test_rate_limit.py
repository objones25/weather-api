from app.weather.schema import WeatherResponse
from app.config import get_settings

settings = get_settings()

def test_under_limit(rate_limit_client, mock_weather_service):
      client, mock_redis = rate_limit_client
      mock_redis.zcard.return_value = 0          # 0 requests in window
      mock_weather_service.get_weather.return_value = WeatherResponse()
      response = client.get("/v1/weather?location=London,UK")
      assert response.status_code == 200

def test_at_limit(rate_limit_client):
    client, mock_redis = rate_limit_client
    mock_redis.zcard.return_value = 60         # at the limit
    response = client.get("/v1/weather?location=London,UK")
    assert response.status_code == 429
    assert response.json()["detail"] == "Rate limit exceeded"



