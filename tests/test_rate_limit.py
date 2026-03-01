from app.weather.schema import WeatherResponse
from app.config import get_settings

settings = get_settings()

def test_under_limit(rate_limit_client, mock_weather_service):
      client, mock_redis = rate_limit_client
      mock_redis.zcard.return_value = 0          # 0 requests in window
      mock_redis.zrange.return_value = []   # empty → uses fallback reset time 
      mock_weather_service.get_weather.return_value = WeatherResponse()
      response = client.get("/v1/weather?location=London,UK")
      assert response.status_code == 200
      assert response.headers["X-RateLimit-Limit"] == "60"
      assert response.headers["X-RateLimit-Remaining"] == "60"
      assert "X-RateLimit-Reset" in response.headers

def test_at_limit(rate_limit_client):
    client, mock_redis = rate_limit_client
    mock_redis.zcard.return_value = 60         # at the limit
    mock_redis.zrange.return_value = []   # empty → uses fallback reset time 
    response = client.get("/v1/weather?location=London,UK")
    assert response.status_code == 429
    assert response.json()["detail"] == "Rate limit exceeded"
    assert "Retry-After" in response.headers
    assert response.headers["X-RateLimit-Remaining"] == "0"



