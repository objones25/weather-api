# Weather API

An async FastAPI wrapper around the [Visual Crossing Timeline Weather API](https://www.visualcrossing.com/resources/documentation/weather-api/timeline-weather-api/) with Redis caching.

## Features

- Fetch current, historical, and forecast weather data for any location
- Redis caching with configurable TTL — repeated requests served in ~100ms vs ~400ms from the upstream API
- Full Pydantic v2 validation on requests and responses
- Async throughout — `httpx.AsyncClient` for HTTP, `redis.asyncio` for cache
- Managed client lifecycles via FastAPI lifespan

## Project Structure

```
app/
├── main.py              # FastAPI app, lifespan (http + redis clients), root/health endpoints
├── config.py            # Pydantic Settings, loaded from .env
├── cache/
│   └── service.py       # CacheService — Redis get/set/delete with MD5 request key hashing
└── weather/
    ├── schema.py        # WeatherRequest (with enums + validation) and WeatherResponse models
    ├── service.py       # WeatherService — cache-first fetch, URL/param building
    └── routes.py        # /v1/weather endpoint
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

# Optional overrides (defaults shown)
WEATHER_API_URL=https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline
REDIS_HOST=your_redis_host
REDIS_PORT=6379
REDIS_USERNAME=default
CACHE_TTL=3600
```

### Run

```bash
fastapi dev app/main.py
```

API docs available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | App name, description, version |
| `GET` | `/health` | Status, version, UTC timestamp |
| `GET` | `/v1/weather` | Fetch weather data |

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
curl "http://localhost:8000/v1/weather?location=London,UK"

# Temperature only for a date range
curl "http://localhost:8000/v1/weather?location=New+York&date1=2026-01-01&date2=2026-01-07&elements=datetime,tempmax,tempmin,temp"

# Current conditions only
curl "http://localhost:8000/v1/weather?location=Tokyo&include=current"
```

## Architecture Notes

### Lifespan-managed clients

Both `httpx.AsyncClient` and `redis.asyncio.Redis` are created once at startup and closed at shutdown via FastAPI's `lifespan` context manager. They are stored on `app.state` and injected into services via `Depends()`.

### Cache key strategy

Each `WeatherRequest` is deterministically serialized to JSON (`model_dump(mode="json")`, `sort_keys=True`) and MD5-hashed to produce a fixed-length Redis key. Any change to request parameters produces a different key.

### Cache-first flow

```
Request → CacheService.get() → hit  → deserialize → return WeatherResponse
                              → miss → Visual Crossing API → CacheService.set() → return WeatherResponse
```
