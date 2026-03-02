import pytest
from app.config import get_settings

settings = get_settings()

ENDPOINTS = [
    ("get", "/health"),
    ("get", "/"),
    ("get", "/v1/weather"),
    ("get", "/v1/cache"),
    ("post", "/v1/cache"),
    ("delete", "/v1/cache"),
]

SAFE_ENDPOINTS = [
    ("get", "/health"),
    ("get", "/"),
]


@pytest.mark.parametrize("method,path", ENDPOINTS)
def test_missing_key_returns_401(raw_client, method, path):
    response = getattr(raw_client, method)(path)
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


@pytest.mark.parametrize("method,path", ENDPOINTS)
def test_invalid_key_returns_401(raw_client, method, path):
    response = getattr(raw_client, method)(path, headers={"X-API-Key": "invalid"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API key"


@pytest.mark.parametrize("method,path", SAFE_ENDPOINTS)
def test_valid_key_returns_200(raw_client, method, path):
    response = getattr(raw_client, method)(
        path, headers={"X-API-Key": settings.api_key}
    )
    assert response.status_code == 200
