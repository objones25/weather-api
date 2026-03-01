from app.config import Settings, get_settings
from app.weather.schema import WeatherRequest, WeatherResponse
from httpx import AsyncClient, HTTPStatusError, RequestError
from fastapi import Depends, HTTPException, Request
from app.cache.service import CacheService, get_cache_service
import logging

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
        cached = await self.cache_service.get(request)
        if cached:
            logger.debug("Cache hit for %s", request.location)
            return WeatherResponse.model_validate_json(cached)
        logger.debug("Cache miss for %s — fetching from API", request.location)
        url = self._build_url(request)
        params = self._build_params(request)
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            weather_response = WeatherResponse.model_validate(response.json())
            await self.cache_service.set(request, weather_response)
            logger.info("Fetched and cached weather for %s", request.location)
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