# Weather API

An async FastAPI wrapper around the [Visual Crossing Timeline Weather API](https://www.visualcrossing.com/resources/documentation/weather-api/timeline-weather-api/) with Redis caching.

## Features

- Fetch current, historical, and forecast weather data for any location
- Redis caching with configurable TTL — repeated requests served in ~100ms vs ~400ms from the upstream API
- Full Pydantic v2 validation on requests and responses
- Async throughout — `httpx.AsyncClient` for HTTP, `redis.asyncio` for cache
- Managed client lifecycles via FastAPI lifespan
- API key authentication via `X-API-Key` header
- Centralised logging — plain-text in development, JSON in production
- Request timing and request ID middleware (`X-Process-Time`, `X-Request-ID` headers)

## Project Structure

```text
app/
├── main.py              # FastAPI app, lifespan, exception handler and middleware registration
├── config.py            # Pydantic Settings, loaded from .env
├── auth.py              # API key authentication dependency
├── logging.py           # setup_logging() — dictConfig, dev/prod formatters
├── exceptions.py        # Custom HTTP and validation exception handlers
├── middleware.py        # TimingMiddleware, RequestIDMiddleware
├── cache/
│   ├── service.py       # CacheService — Redis get/set/delete with MD5 request key hashing
│   └── routes.py        # /v1/cache GET/POST/DELETE endpoints
└── weather/
    ├── schema.py        # WeatherRequest (with enums + validation) and WeatherResponse models
    ├── service.py       # WeatherService — cache-first fetch, URL/param building
    └── routes.py        # /v1/weather endpoint
tests/
├── conftest.py          # Shared fixtures — TestClient, mock services
├── test_main.py         # Root and health endpoint tests
├── test_auth.py         # Auth tests — missing/invalid/valid key
├── test_weather.py      # Weather endpoint tests
└── test_cache.py        # Cache endpoint tests
```

## Setup

### Requirements

- Python 3.13+
- [uv](https://github.com/astral-sh/uv)
- A [Visual Crossing API key](https://www.visualcrossing.com/weather-data-editions/)
- A Redis instance

### Install dependencies

```bash
uv sync
```

### Configure environment

Create a `.env` file in the project root:

```env
WEATHER_API_KEY=your_visual_crossing_api_key
REDIS_PASSWORD=your_redis_password
API_KEY=your_api_key

# Optional overrides (defaults shown)
WEATHER_API_URL=https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline
REDIS_HOST=your_redis_host
REDIS_PORT=6379
REDIS_USERNAME=default
CACHE_TTL=43200
ENVIRONMENT=development
LOG_LEVEL=DEBUG
```

### Run

```bash
fastapi dev app/main.py
```

API docs available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### Run tests

```bash
uv run pytest tests/ -v
```

## Endpoints

All endpoints require an `X-API-Key` header.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | App name, description, version |
| `GET` | `/health` | Status, version, UTC timestamp |
| `GET` | `/v1/weather` | Fetch weather data |
| `GET` | `/v1/cache` | Retrieve a cached response |
| `POST` | `/v1/cache` | Store a response in cache |
| `DELETE` | `/v1/cache` | Delete a cached response |

### Weather endpoint parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `location` | string | Yes | — | Address, lat/lon, ZIP, or city name |
| `date1` | string | No | — | Start date (`yyyy-MM-dd`), UNIX timestamp, or keyword (`today`, `last30days`) |
| `date2` | string | No | — | End date — requires `date1` |
| `unit_group` | enum | No | `us` | Unit system: `us`, `uk`, `metric`, `base` |
| `include` | list | No | — | Sections to include: `days`, `hours`, `current`, `alerts`, `obs`, etc. |
| `elements` | list | No | — | Specific fields to return — supports `add:element` / `remove:element` |
| `lang` | enum | No | `en` | Response language — 28 languages supported |

### Example requests

```bash
# 15-day forecast for London
curl -H "X-API-Key: your_key" "http://localhost:8000/v1/weather?location=London,UK"

# Temperature only for a date range
curl -H "X-API-Key: your_key" "http://localhost:8000/v1/weather?location=New+York&date1=2026-01-01&date2=2026-01-07&elements=datetime,tempmax,tempmin,temp"

# Current conditions only
curl -H "X-API-Key: your_key" "http://localhost:8000/v1/weather?location=Tokyo&include=current"
```

## Architecture Notes

### Lifespan-managed clients

Both `httpx.AsyncClient` and `redis.asyncio.Redis` are created once at startup and closed at shutdown via FastAPI's `lifespan` context manager. They are stored on `app.state` and injected into services via `Depends()`.

### Cache key strategy

Each `WeatherRequest` is deterministically serialized to JSON (`model_dump(mode="json")`, `sort_keys=True`) and MD5-hashed to produce a fixed-length Redis key. Any change to request parameters produces a different key.

### Cache-first flow

```text
Request → CacheService.get() → hit  → deserialize → return WeatherResponse
                              → miss → Visual Crossing API → CacheService.set() → return WeatherResponse
```

### Middleware execution order

Middleware is registered LIFO — `RequestIDMiddleware` runs first (sets `request.state.request_id`), then `TimingMiddleware` (reads the ID for its log line).
