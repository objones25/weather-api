import asyncio
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from app.cache.schema import CacheWarmRequest, CacheWarmResponse, CacheWarmError
from app.cache.service import CacheService, get_cache_service
from app.weather.schema import WeatherRequest, WeatherResponse
from app.weather.service import WeatherService, get_weather_service

router = APIRouter(
    prefix="/v1",
    tags=["Cache"],
)


@router.get("/cache", response_model=WeatherResponse)
async def get_cache(
    request: WeatherRequest = Depends(),
    cache_service: CacheService = Depends(get_cache_service),
):
    result = await cache_service.get(request)
    if result.value is None:
        raise HTTPException(status_code=404, detail="No cached entry for this request")
    return WeatherResponse.model_validate_json(result.value)


@router.post("/cache")
async def set_cache(
    response: WeatherResponse,
    request: Annotated[WeatherRequest, Query()],
    cache_service: CacheService = Depends(get_cache_service),
):
    await cache_service.set(request, response)


@router.delete("/cache")
async def delete_cache(
    request: WeatherRequest = Depends(),
    cache_service: CacheService = Depends(get_cache_service),
):
    await cache_service.delete(request)


@router.post("/cache/warm", response_model=CacheWarmResponse)
async def warm_cache(
    body: CacheWarmRequest,
    weather_service: WeatherService = Depends(get_weather_service),
) -> CacheWarmResponse:
    """Pre-populate the cache for up to 50 locations.

    Fetches all locations concurrently via asyncio.gather.  Already-cached
    locations are served from cache (no upstream call) and counted as succeeded.
    Returns a summary once all fetches complete.
    """
    outcomes = await asyncio.gather(
        *[weather_service.get_weather(loc) for loc in body.locations],
        return_exceptions=True,
    )
    errors: list[CacheWarmError] = []
    succeeded = 0
    for req, outcome in zip(body.locations, outcomes):
        if isinstance(outcome, Exception):
            detail = (
                str(outcome.detail)
                if isinstance(outcome, HTTPException)
                else str(outcome)
            )
            errors.append(CacheWarmError(location=req.location, detail=detail))
        else:
            succeeded += 1
    return CacheWarmResponse(
        total=len(body.locations),
        succeeded=succeeded,
        failed=len(errors),
        errors=errors,
    )
