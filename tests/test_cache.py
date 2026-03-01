import pytest
from app.config import get_settings
from app.weather.schema import WeatherResponse
import json

settings = get_settings()


def test_cache_get(client, mock_cache_service):                                                                      
      mock_cache_service.get.return_value = json.dumps(WeatherResponse().model_dump(mode="json"))                      
      response = client.get("/v1/cache?location=London,UK")                                                          
      assert response.status_code == 200                                                                               
      data = response.json()
      assert data["days"] == []
      assert data["alerts"] == []
      assert data["queryCost"] is None

def test_cache_miss(client, mock_cache_service):
    mock_cache_service.get.return_value = None
    response = client.get("/v1/cache?location=London,UK")
    assert response.status_code == 404
    assert response.json()["detail"] == "No cached entry for this request"

def test_cache_set(client, mock_cache_service):
    mock_cache_service.set.return_value = None
    body = WeatherResponse().model_dump(mode="json")
    response = client.post("/v1/cache?location=London,UK", json=body)
    assert response.status_code == 200

def test_cache_delete(client, mock_cache_service):
    mock_cache_service.delete.return_value = None
    response = client.delete("/v1/cache?location=London,UK")
    assert response.status_code == 200