from app.config import Settings, get_settings
from app.weather.schema import WeatherRequest, WeatherResponse
from httpx import AsyncClient, HTTPStatusError, RequestError
from fastapi import Depends, HTTPException, Request
from app.cache.service import CacheService, get_cache_service
import logging
import time

logger = logging.getLogger(__name__)

class WeatherService:
    def __init__(self, client: AsyncClient, cache_service: CacheService, settings: Settings) -> None:
        self.client = client
        self.cache_service = cache_service
        self.api_url = settings.weather_api_url
    def _build_url(self, request: WeatherRequest) -> str:
        parts = [
            self.api_url,
            request.location,
            request.date1,
            request.date2,
        ]
        url = "/".join(filter(None, parts))
        return url
    
    def _build_params(self, request: WeatherRequest) -> dict:
        params = {
            "unitGroup": request.unit_group.value,
            "lang": request.lang.value,
        }

        if request.include:
            params["include"] = ",".join(i.value for i in request.include)

        if request.elements:
            params["elements"] = ",".join(request.elements)

        return params
    
    async def get_weather(self, request: WeatherRequest) -> WeatherResponse:
        t0 = time.perf_counter()
        cached = await self.cache_service.get(request)
        t1 = time.perf_counter()

        if cached:
            result = WeatherResponse.model_validate_json(cached)
            t2 = time.perf_counter()
            logger.debug(
                "Cache hit for %s [redis=%dms parse=%dms total=%dms]",
                request.location,
                int((t1 - t0) * 1000),
                int((t2 - t1) * 1000),
                int((t2 - t0) * 1000),
            )
            return result

        logger.debug("Cache miss for %s [redis=%dms] — fetching from API", request.location, int((t1 - t0) * 1000))
        url = self._build_url(request)
        params = self._build_params(request)
        try:
            t2 = time.perf_counter()
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            t3 = time.perf_counter()
            weather_response = WeatherResponse.model_validate(response.json())
            t4 = time.perf_counter()
            await self.cache_service.set(request, weather_response)
            t5 = time.perf_counter()
            logger.info(
                "Fetched and cached weather for %s [api=%dms parse=%dms cache_set=%dms total=%dms]",
                request.location,
                int((t3 - t2) * 1000),
                int((t4 - t3) * 1000),
                int((t5 - t4) * 1000),
                int((t5 - t0) * 1000),
            )
            return weather_response
        except HTTPStatusError as e:
            logger.error("Upstream API error for %s: %d %s", request.location, e.response.status_code, e.response.text)
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        except RequestError as e:
            logger.error("Network error reaching weather API for %s: %s", request.location, e)
            raise HTTPException(status_code=503, detail=f"Could not reach weather service: {e}")
       

def get_weather_service(request: Request, settings: Settings = Depends(get_settings)) -> WeatherService:
    cache_service = get_cache_service(request, settings)
    return WeatherService(request.app.state.http_client, cache_service, settings)