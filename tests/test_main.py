from app.config import get_settings

settings = get_settings()


def _assert_health_shape(data):
    assert data["version"] == settings.app_version
    assert isinstance(data["timestamp"], str)
    for key in ("redis", "weather_api"):
        assert isinstance(data["checks"][key]["latency_ms"], int)
        assert data["checks"][key]["latency_ms"] >= 0


def test_metrics_endpoint(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    # Default Python/process metrics are always present
    assert "python_info" in response.text
    # Our custom metric families are registered even before first observation
    assert "http_request_duration_seconds" in response.text
    assert "cache_requests_total" in response.text


def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == settings.app_name
    assert data["description"] == settings.app_description
    assert data["version"] == settings.app_version


def test_health_both_healthy(health_client):
    client, mock_redis, mock_http_client = health_client
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["checks"]["redis"]["status"] == "ok"
    assert data["checks"]["weather_api"]["status"] == "ok"
    _assert_health_shape(data)


def test_health_redis_down(health_client):
    client, mock_redis, mock_http_client = health_client
    mock_redis.ping.side_effect = Exception("connection refused")
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["checks"]["redis"]["status"] == "unavailable"
    assert data["checks"]["weather_api"]["status"] == "ok"
    _assert_health_shape(data)


def test_health_api_down(health_client):
    client, mock_redis, mock_http_client = health_client
    mock_http_client.head.side_effect = Exception("connection refused")
    response = client.get("/health")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unavailable"
    assert data["checks"]["redis"]["status"] == "ok"
    assert data["checks"]["weather_api"]["status"] == "unavailable"
    _assert_health_shape(data)


def test_health_both_down(health_client):
    client, mock_redis, mock_http_client = health_client
    mock_redis.ping.side_effect = Exception("connection refused")
    mock_http_client.head.side_effect = Exception("connection refused")
    response = client.get("/health")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unavailable"
    assert data["checks"]["redis"]["status"] == "unavailable"
    assert data["checks"]["weather_api"]["status"] == "unavailable"
    _assert_health_shape(data)
