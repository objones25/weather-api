from redis.asyncio.client import Redis
from fastapi import Depends, Request
from app.config import Settings, get_settings
from app.weather.schema import WeatherRequest, WeatherResponse
from hashlib import md5
import json

class CacheService:
    def __init__(self, settings: Settings, client: Redis) -> None:
        self.client = client
        self.cache_ttl = settings.cache_ttl

    def _create_key(self, request: WeatherRequest) -> str:
        return md5(json.dumps(request.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()

    async def get(self, request: WeatherRequest) -> str:
        key = self._create_key(request)
        return await self.client.get(key)

    async def set(self, request: WeatherRequest, response: WeatherResponse) -> None:
        key = self._create_key(request)
        value = json.dumps(response.model_dump(mode="json"))
        await self.client.set(key, value, ex=self.cache_ttl)

    async def delete(self, request: WeatherRequest) -> None:
        key = self._create_key(request)
        await self.client.delete(key)


def get_cache_service(request: Request, settings: Settings = Depends(get_settings)) -> CacheService:
    return CacheService(settings, request.app.state.redis_client)