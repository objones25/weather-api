from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from app.cache.service import CacheService, get_cache_service
from app.weather.schema import WeatherRequest, WeatherResponse

router = APIRouter(
    prefix="/v1",
    tags=["Cache"],
)

@router.get("/cache", response_model=WeatherResponse)
async def get_cache(request: WeatherRequest = Depends(), cache_service: CacheService = Depends(get_cache_service)):
    result = await cache_service.get(request)
    if result.value is None:
        raise HTTPException(status_code=404, detail="No cached entry for this request")
    return WeatherResponse.model_validate_json(result.value)

@router.post("/cache")
async def set_cache(response: WeatherResponse, request: Annotated[WeatherRequest, Query()], cache_service: CacheService = Depends(get_cache_service)):
    await cache_service.set(request, response)

@router.delete("/cache")
async def delete_cache(request: WeatherRequest = Depends(), cache_service: CacheService = Depends(get_cache_service)):
    await cache_service.delete(request)