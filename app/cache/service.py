from redis.asyncio.client import Redis
from fastapi import Depends, Request
from app.config import Settings, get_settings
from app.weather.schema import WeatherRequest, WeatherResponse
from app.metrics import CACHE_REQUESTS_TOTAL
from hashlib import md5
import json
import logging

logger = logging.getLogger(__name__)

class CacheService:
    def __init__(self, settings: Settings, client: Redis) -> None:
        self.client = client
        self.cache_ttl = settings.cache_ttl

    def _create_key(self, request: WeatherRequest) -> str:
        return md5(json.dumps(request.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()

    async def get(self, request: WeatherRequest) -> str:
        key = self._create_key(request)
        result = await self.client.get(key)
        CACHE_REQUESTS_TOTAL.labels(result="hit" if result is not None else "miss").inc()
        return result

    async def set(self, request: WeatherRequest, response: WeatherResponse) -> None:
        key = self._create_key(request)
        value = response.model_dump_json()
        await self.client.set(key, value, ex=self.cache_ttl)
        logger.debug("Cache set for %s (ttl=%ds)", request.location, self.cache_ttl)

    async def delete(self, request: WeatherRequest) -> None:
        key = self._create_key(request)
        await self.client.delete(key)
        logger.debug("Cache deleted for %s", request.location)


def get_cache_service(request: Request, settings: Settings = Depends(get_settings)) -> CacheService:
    return CacheService(settings, request.app.state.redis_client)