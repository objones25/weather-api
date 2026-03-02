from app.config import get_settings
from app.logging import setup_logging
from app.telemetry import setup_tracing, instrument_sqlalchemy
from app.exceptions import (
    custom_http_exception_handler,
    custom_validation_exception_handler,
)
from app.middleware import TimingMiddleware, RequestIDMiddleware
from app.auth import verify_api_key
from app.rate_limit import check_rate_limit
from app.database import init_db
from fastapi import FastAPI, Depends, Request, Response
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from datetime import datetime, timezone
from app.weather.routes import router as weather_router
from app.cache.routes import router as cache_router
from app.history.routes import router as history_router
from contextlib import asynccontextmanager
from httpx import AsyncClient
from redis.asyncio.client import Redis
from prometheus_client import make_asgi_app
import asyncio
import time

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings)
    # setup_tracing before clients are created so httpx/Redis monkey-patching
    # is in place when those clients are instantiated below.
    setup_tracing(app, settings)
    app.state.http_client = AsyncClient(params={"key": settings.weather_api_key})
    app.state.redis_client = Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        username=settings.redis_username,
        password=settings.redis_password,
        decode_responses=True,
    )
    app.state.db_engine, app.state.db_session_factory = await init_db(settings)
    # instrument_sqlalchemy after the engine exists — it needs the sync_engine reference.
    instrument_sqlalchemy(app.state.db_engine, settings)
    yield
    await app.state.http_client.aclose()
    await app.state.redis_client.aclose()
    await app.state.db_engine.dispose()


app = FastAPI(
    title=settings.app_name,
    description=settings.app_description,
    version=settings.app_version,
    lifespan=lifespan,
    dependencies=[Depends(verify_api_key), Depends(check_rate_limit)],
)

app.include_router(weather_router)
app.include_router(cache_router)
app.include_router(history_router)

# Mounted as a sub-app so FastAPI's global auth/rate-limit dependencies don't apply.
# Prometheus scrapers don't send API keys, so this endpoint must be unauthenticated.
app.mount("/metrics", make_asgi_app())

app.add_exception_handler(StarletteHTTPException, custom_http_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, custom_validation_exception_handler)  # type: ignore[arg-type]

# RequestIDMiddleware registered last so it runs first (LIFO), ensuring
# request.state.request_id is set before TimingMiddleware needs it
app.add_middleware(TimingMiddleware)
app.add_middleware(RequestIDMiddleware)


@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "description": settings.app_description,
        "version": settings.app_version,
    }


async def _check(coro) -> dict:
    now = time.time()
    try:
        await coro
        return {"status": "ok", "latency_ms": int((time.time() - now) * 1000)}
    except Exception:
        return {"status": "unavailable", "latency_ms": int((time.time() - now) * 1000)}


@app.get("/health")
async def health(request: Request, response: Response):
    redis_result, weather_result = await asyncio.gather(
        _check(request.app.state.redis_client.ping()),
        _check(request.app.state.http_client.head(settings.weather_api_url)),
    )

    if weather_result["status"] == "unavailable":
        overall, response.status_code = "unavailable", 503
    elif redis_result["status"] == "unavailable":
        overall = "degraded"
    else:
        overall = "ok"

    return {
        "status": overall,
        "version": settings.app_version,
        "timestamp": datetime.now(timezone.utc),
        "checks": {"redis": redis_result, "weather_api": weather_result},
    }
