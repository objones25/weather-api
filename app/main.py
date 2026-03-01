from app.config import get_settings
from fastapi import FastAPI
from datetime import datetime, timezone
from app.weather.routes import router as weather_router
from app.cache.routes import router as cache_router
from contextlib import asynccontextmanager
from httpx import AsyncClient
from redis.asyncio.client import Redis

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = AsyncClient(params={"key": settings.weather_api_key})
    app.state.redis_client = Redis(host=settings.redis_host, port=settings.redis_port, username=settings.redis_username, password=settings.redis_password, decode_responses=True)
    yield
    await app.state.http_client.aclose()
    await app.state.redis_client.aclose()

app = FastAPI(title=settings.app_name, description=settings.app_description, version=settings.app_version, lifespan=lifespan)

app.include_router(weather_router)
app.include_router(cache_router)

@app.get("/")
async def root():
    return {
        "app_name": settings.app_name, 
        "app_description": settings.app_description, 
        "app_version": settings.app_version,
        }

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "app_version": settings.app_version,
        "timestamp": datetime.now(timezone.utc),
        }