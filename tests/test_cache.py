import json
from fastapi import HTTPException
from app.config import get_settings
from app.weather.schema import WeatherResponse
from app.cache.service import CacheResult

settings = get_settings()


def test_cache_get(client, mock_cache_service):
    mock_cache_service.get.return_value = CacheResult(
        value=json.dumps(WeatherResponse().model_dump(mode="json"))
    )
    response = client.get("/v1/cache?location=London,UK")
    assert response.status_code == 200
    data = response.json()
    assert data["days"] == []
    assert data["alerts"] == []
    assert data["queryCost"] is None


def test_cache_miss(client, mock_cache_service):
    mock_cache_service.get.return_value = CacheResult(value=None)
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


# ---------------------------------------------------------------------------
# POST /v1/cache/warm
# ---------------------------------------------------------------------------


def test_warm_cache_success(client, mock_weather_service):
    mock_weather_service.get_weather.return_value = WeatherResponse()
    response = client.post(
        "/v1/cache/warm",
        json={"locations": [{"location": "London,UK"}, {"location": "Paris,FR"}]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["succeeded"] == 2
    assert data["failed"] == 0
    assert data["errors"] == []


def test_warm_cache_partial_failure(client, mock_weather_service):
    mock_weather_service.get_weather.side_effect = [
        WeatherResponse(),
        HTTPException(status_code=404, detail="Location not found"),
    ]
    response = client.post(
        "/v1/cache/warm",
        json={"locations": [{"location": "London,UK"}, {"location": "BadCity"}]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["succeeded"] == 1
    assert data["failed"] == 1
    assert data["errors"][0]["location"] == "BadCity"
    assert data["errors"][0]["detail"] == "Location not found"


def test_warm_cache_all_fail(client, mock_weather_service):
    mock_weather_service.get_weather.side_effect = HTTPException(
        status_code=503, detail="Upstream unavailable"
    )
    response = client.post(
        "/v1/cache/warm",
        json={"locations": [{"location": "London,UK"}]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["succeeded"] == 0
    assert data["failed"] == 1
    assert data["errors"][0]["detail"] == "Upstream unavailable"


def test_warm_cache_empty_list(client):
    response = client.post("/v1/cache/warm", json={"locations": []})
    assert response.status_code == 422


def test_warm_cache_exceeds_max(client):
    locations = [{"location": f"City{i}"} for i in range(51)]
    response = client.post("/v1/cache/warm", json={"locations": locations})
    assert response.status_code == 422
