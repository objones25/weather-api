from dataclasses import dataclass
from hashlib import md5
from redis.asyncio.client import Redis
from fastapi import Depends, Request
from app.config import Settings, get_settings
from app.weather.schema import WeatherRequest, WeatherResponse
from app.metrics import CACHE_REQUESTS_TOTAL
import json
import logging
import re

logger = logging.getLogger(__name__)


@dataclass
class CacheResult:
    value: str | None
    needs_refresh: bool = False


class CacheService:
    def __init__(self, settings: Settings, client: Redis) -> None:
        self.client = client
        self.cache_ttl = settings.cache_ttl
        self.warm_threshold = settings.cache_warm_threshold

    @staticmethod
    def _normalize_location(location: str) -> str:
        """Lowercase and normalise whitespace/comma spacing for consistent cache keys.

        Handles the most common spelling variants — case, extra spaces, and
        irregular spacing around commas — so "New York , NY" and "new york,ny"
        both produce the same key.  Does not resolve aliases (e.g. "NYC"); that
        is handled by the resolvedAddress alias written in set().
        """
        loc = location.strip().lower()
        loc = re.sub(r"\s+", " ", loc)
        loc = re.sub(r"\s*,\s*", ", ", loc)
        return loc

    def _create_key(self, request: WeatherRequest) -> str:
        data = request.model_dump(mode="json")
        data["location"] = self._normalize_location(data["location"])
        return md5(json.dumps(data, sort_keys=True).encode()).hexdigest()

    async def get(self, request: WeatherRequest) -> CacheResult:
        key = self._create_key(request)
        # GET and TTL in one pipeline round-trip so warming adds no extra latency.
        async with self.client.pipeline() as pipe:
            pipe.get(key)
            pipe.ttl(key)
            value, ttl = await pipe.execute()

        if value is None:
            CACHE_REQUESTS_TOTAL.labels(result="miss").inc()
            return CacheResult(value=None)

        CACHE_REQUESTS_TOTAL.labels(result="hit").inc()
        warm_threshold_secs = int(self.cache_ttl * self.warm_threshold)
        needs_refresh = 0 <= ttl <= warm_threshold_secs
        return CacheResult(value=value, needs_refresh=needs_refresh)

    async def set(self, request: WeatherRequest, response: WeatherResponse) -> None:
        key = self._create_key(request)
        value = response.model_dump_json()
        await self.client.set(key, value, ex=self.cache_ttl)
        logger.debug("Cache set for %s (ttl=%ds)", request.location, self.cache_ttl)

        # Write a resolvedAddress alias so different spellings of the same place
        # (e.g. "nyc" after "New York, NY, United States" was first queried) hit
        # the cache on subsequent requests — no extra upstream call needed.
        if response.resolvedAddress:
            resolved_request = request.model_copy(
                update={"location": response.resolvedAddress}
            )
            resolved_key = self._create_key(resolved_request)
            if resolved_key != key:
                await self.client.set(resolved_key, value, ex=self.cache_ttl)
                logger.debug(
                    "Cache alias set %s → %s",
                    request.location,
                    response.resolvedAddress,
                )

    async def delete(self, request: WeatherRequest) -> None:
        key = self._create_key(request)
        await self.client.delete(key)
        logger.debug("Cache deleted for %s", request.location)


def get_cache_service(
    request: Request, settings: Settings = Depends(get_settings)
) -> CacheService:
    return CacheService(settings, request.app.state.redis_client)
