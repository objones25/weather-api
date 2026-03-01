import pytest
from app.config import get_settings
settings = get_settings()

def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["app_version"] == settings.app_version
    assert data["app_description"] == settings.app_description
    assert data["app_name"] == settings.app_name
    
def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app_version"] == settings.app_version
    assert isinstance(data["timestamp"], str)