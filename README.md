# Weather API

An async FastAPI wrapper around the [Visual Crossing Timeline Weather API](https://www.visualcrossing.com/resources/documentation/weather-api/timeline-weather-api/) with Redis caching and SQLite request history.

## Features

- Fetch current, historical, and forecast weather data for any location
- Redis caching with configurable TTL — repeated requests served in ~100ms vs ~400ms from the upstream API
- Request history stored in SQLite — queryable with location filter and offset pagination
- Sliding window rate limiting via Redis sorted sets (`X-RateLimit-*` headers)
- Prometheus metrics exposed at `/metrics` — HTTP request counts, latency histograms, cache hit/miss counters, rate limit rejections
- Full Pydantic v2 validation on requests and responses
- Async throughout — `httpx.AsyncClient` for HTTP, `redis.asyncio` for cache, `aiosqlite` for history
- Database migrations managed by Alembic — schema versioned and applied at deployment
- Managed client lifecycles via FastAPI lifespan
- API key authentication via `X-API-Key` header
- Centralised logging — plain-text in development, JSON in production
- Request timing and request ID middleware (`X-Process-Time`, `X-Request-ID` headers)
- Deep health check endpoint reporting Redis and upstream API status

## Project Structure

```text
app/
├── main.py              # FastAPI app, lifespan, exception handler and middleware registration
├── config.py            # Pydantic Settings, loaded from .env
├── auth.py              # API key authentication dependency
├── rate_limit.py        # Sliding window rate limiter dependency
├── metrics.py           # Prometheus metric definitions (Counter, Histogram)
├── telemetry.py         # OpenTelemetry setup — tracer provider, FastAPI/httpx/Redis/SQLAlchemy instrumentation
├── database.py          # Async SQLite engine init, get_session dependency
alembic/
├── env.py               # Async-compatible migration environment
└── versions/            # Versioned migration scripts
├── logging.py           # setup_logging() — dictConfig, dev/prod formatters
├── exceptions.py        # Custom HTTP and validation exception handlers
├── middleware.py        # TimingMiddleware, RequestIDMiddleware (pure ASGI) — records HTTP metrics
├── cache/
│   ├── service.py       # CacheService — Redis get/set/delete with MD5 request key hashing
│   └── routes.py        # /v1/cache GET/POST/DELETE endpoints
├── history/
│   ├── models.py        # RequestLog SQLModel table
│   ├── service.py       # HistoryService — list with filter and pagination
│   └── routes.py        # /v1/history GET endpoint
└── weather/
    ├── schema.py        # WeatherRequest (with enums + validation) and WeatherResponse models
    ├── service.py       # WeatherService — cache-first fetch, URL/param building
    └── routes.py        # /v1/weather endpoint, logs requests as background task
tests/
├── conftest.py               # Shared fixtures — TestClient, mock services, async DB
├── test_main.py              # Root, health, and metrics endpoint tests
├── test_auth.py              # Auth tests — missing/invalid/valid key
├── test_weather.py           # Weather endpoint + WeatherRequest validator unit tests
├── test_weather_service.py   # WeatherService unit tests (mocked httpx + cache)
├── test_cache.py             # Cache endpoint tests
├── test_cache_service.py     # CacheService unit tests (mocked Redis)
├── test_rate_limit.py        # Rate limit header and 429 tests
├── test_history.py           # History endpoint tests
├── test_telemetry.py         # Telemetry unit tests (mocked OTel packages)
└── test_benchmarks.py        # pytest-benchmark micro-benchmarks (excluded from CI)
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
CACHE_WARM_THRESHOLD=0.2
RATE_LIMIT_REQUESTS=60
RATE_LIMIT_WINDOW=60
ENVIRONMENT=development
LOG_LEVEL=DEBUG
DATABASE_URL=sqlite+aiosqlite:///./history.db

# OpenTelemetry tracing (disabled by default)
OTEL_ENABLED=false
OTEL_ENDPOINT=http://localhost:4318
OTEL_SERVICE_NAME=weather-api
```

### Run

```bash
# Apply migrations, then start the dev server
alembic upgrade head
fastapi dev app/main.py
```

API docs available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### Run tests

```bash
uv run pytest tests/ --ignore=tests/test_benchmarks.py -v
```

72 tests, 99% coverage. Benchmarks are excluded from the default run to keep it fast and deterministic — see [Run benchmarks](#run-benchmarks) below.

### Run with Docker

Requires Docker and Docker Compose. Set `WEATHER_API_KEY` and `API_KEY` in `.env` — Redis is provided by the compose stack so no external instance is needed.

```bash
docker compose up --build
```

API docs available at [http://localhost:8000/docs](http://localhost:8000/docs)

Request history is persisted in a named Docker volume (`sqlite_data`) so it survives container restarts. Redis is not exposed to the host — services communicate over an internal `backend` network.

To run with distributed tracing, add Jaeger via the `tracing` profile and enable OTel in `.env`:

```bash
# .env additions
OTEL_ENABLED=true
OTEL_ENDPOINT=http://jaeger:4318

docker compose --profile tracing up --build
```

Jaeger UI available at [http://localhost:16686](http://localhost:16686)

## Endpoints

All endpoints require an `X-API-Key` header except `/metrics`.

| Method   | Path          | Auth required | Description                          |
| -------- | ------------- | ------------- | ------------------------------------ |
| `GET`    | `/`           | Yes           | App name, description, version       |
| `GET`    | `/health`     | Yes           | Deep health check (Redis + API)      |
| `GET`    | `/v1/weather` | Yes           | Fetch weather data                   |
| `GET`    | `/v1/cache`   | Yes           | Retrieve a cached response           |
| `POST`   | `/v1/cache`   | Yes           | Store a response in cache            |
| `DELETE` | `/v1/cache`   | Yes           | Delete a cached response             |
| `GET`    | `/v1/history` | Yes           | List past weather requests           |
| `GET`    | `/metrics`    | No            | Prometheus metrics (scrape endpoint) |

### Weather endpoint parameters

| Parameter    | Type   | Required | Default | Description                                                                   |
| ------------ | ------ | -------- | ------- | ----------------------------------------------------------------------------- |
| `location`   | string | Yes      | —       | Address, lat/lon, ZIP, or city name                                           |
| `date1`      | string | No       | —       | Start date (`yyyy-MM-dd`), UNIX timestamp, or keyword (`today`, `last30days`) |
| `date2`      | string | No       | —       | End date — requires `date1`                                                   |
| `unit_group` | enum   | No       | `us`    | Unit system: `us`, `uk`, `metric`, `base`                                     |
| `include`    | list   | No       | —       | Sections to include: `days`, `hours`, `current`, `alerts`, `obs`, etc.        |
| `elements`   | list   | No       | —       | Specific fields to return — supports `add:element` / `remove:element`         |
| `lang`       | enum   | No       | `en`    | Response language — 28 languages supported                                    |

### History endpoint parameters

| Parameter  | Type    | Required | Default | Description                       |
| ---------- | ------- | -------- | ------- | --------------------------------- |
| `location` | string  | No       | —       | Case-insensitive substring filter |
| `offset`   | integer | No       | `0`     | Number of records to skip         |
| `limit`    | integer | No       | `20`    | Records to return — max `100`     |

Returns `{ items, total, offset, limit }` where `total` reflects any active filter.

### Example requests

```bash
# 15-day forecast for London
curl -H "X-API-Key: your_key" "http://localhost:8000/v1/weather?location=London,UK"

# Temperature only for a date range
curl -H "X-API-Key: your_key" "http://localhost:8000/v1/weather?location=New+York&date1=2026-01-01&date2=2026-01-07&elements=datetime,tempmax,tempmin,temp"

# Current conditions only
curl -H "X-API-Key: your_key" "http://localhost:8000/v1/weather?location=Tokyo&include=current"

# Recent request history
curl -H "X-API-Key: your_key" "http://localhost:8000/v1/history"

# Filtered and paginated history
curl -H "X-API-Key: your_key" "http://localhost:8000/v1/history?location=london&limit=5&offset=0"
```

## Architecture Notes

### Lifespan-managed clients

`httpx.AsyncClient`, `redis.asyncio.Redis`, and the SQLite async engine are all created once at startup and closed at shutdown via FastAPI's `lifespan` context manager. They are stored on `app.state` and injected into services via `Depends()`.

### Cache key strategy

Each `WeatherRequest` is deterministically serialized to JSON (`model_dump(mode="json")`, `sort_keys=True`) and MD5-hashed to produce a fixed-length Redis key. Any change to request parameters produces a different key.

### Cache-first flow with async warming

```text
Request → CacheService.get() → hit (fresh)          → deserialize → return WeatherResponse
                              → hit (needs refresh)  → deserialize → fire background refresh → return WeatherResponse
                              → miss                 → Visual Crossing API → CacheService.set() → return WeatherResponse
```

`CacheService.get()` fetches the value and its TTL in a single Redis pipeline round-trip. If the remaining TTL falls below `CACHE_WARM_THRESHOLD` (default 20% of `CACHE_TTL`), the cached response is returned immediately and a background task silently refreshes the cache — so the next caller finds a fresh entry without ever waiting on the upstream API.

### Database migrations

Alembic manages all schema changes. Migration scripts live in `alembic/versions/` and are applied with `alembic upgrade head`. The Dockerfile runs this automatically before starting the server. To create a migration after changing a model:

```bash
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

### Request history

Every successful weather request logs a `RequestLog` row (location + timestamp) as a `BackgroundTask` — after the response is sent, with its own database session, so it adds zero latency to the response.

### Rate limiting

Sliding window algorithm using a Redis sorted set per API key:

1. Evict entries older than the window (`ZREMRANGEBYSCORE`)
2. Count remaining entries (`ZCARD`) — reject with 429 if at limit
3. Record this request (`ZADD`) and refresh TTL (`EXPIRE`)

All three read operations are batched into one pipeline round-trip.

### Middleware execution order

Middleware is registered LIFO — `RequestIDMiddleware` runs first (sets `request.state.request_id`), then `TimingMiddleware` (reads the ID for its log line). Both are implemented as pure ASGI middleware (no `BaseHTTPMiddleware`) to avoid response-buffering overhead.

## CI

Two parallel jobs run on every push and pull request to `main`:

| Job | What it does |
|-----|--------------|
| `lint` | `ruff check .` (imports, unused vars, etc.) + `ruff format --check .` (formatting) |
| `test` | Full test suite with `--cov-fail-under=95` — build fails if coverage drops below 95% |

Coverage is also written to the GitHub Actions step summary as a Markdown table.

To run the same checks locally:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/ --ignore=tests/test_benchmarks.py --cov=app --cov-fail-under=95
```

## Performance

Benchmarks were measured with `pytest-benchmark` against a realistic 15-day forecast payload (15 `DailyWeather` objects × 24 `HourlyWeather` each, plus `currentConditions` and station metadata).

| Operation                               | Mean     | Notes                                          |
| --------------------------------------- | -------- | ---------------------------------------------- |
| `WeatherRequest` parsing                | ~851 ns  | Runs on every request — negligible             |
| Cache key generation (MD5)              | ~4.5 μs  | Runs on every request — negligible             |
| `WeatherResponse.model_validate()`      | ~641 μs  | Cache-miss path: dict → model                  |
| `WeatherResponse.model_dump_json()`     | ~714 μs  | Cache-miss path: model → JSON string for Redis |
| `WeatherResponse.model_validate_json()` | ~1.06 ms | Cache-hit path: JSON string → model            |

**CPU cost per request:**

- Cache hit: ~1.06 ms (validation only)
- Cache miss: ~1.36 ms (validation + serialisation) + ~300–600 ms upstream API

Pydantic overhead is under 0.5% of total latency on a cache miss. The main beneficiary of caching is eliminating the upstream API call, not CPU savings.

**Serialisation note:** `CacheService.set()` uses `model_dump_json()` (Pydantic's Rust-backed serialiser) rather than `model_dump(mode="json") + json.dumps()`. This cut serialisation time from ~1.64 ms to ~714 μs — a 2.3× improvement.

### Run benchmarks

```bash
uv run pytest tests/test_benchmarks.py -v --benchmark-sort=mean
```

Benchmarks are excluded from CI (`--ignore=tests/test_benchmarks.py`) to keep the test run fast and deterministic.
