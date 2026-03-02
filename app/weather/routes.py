import logging
from fastapi import APIRouter, Depends, BackgroundTasks, Request, Response
from app.config import Settings, get_settings
from app.rate_limit import check_batch_rate_limit
from app.weather.service import get_weather_service, WeatherService
from app.weather.schema import (
    BatchWeatherRequest,
    BatchWeatherResponse,
    WeatherRequest,
    WeatherResponse,
)
from app.history.models import RequestLog

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1",
    tags=["Weather"],
)


async def _log_request(session_factory, location: str) -> None:
    try:
        async with session_factory() as session:
            session.add(RequestLog(location=location))
            await session.commit()
    except Exception:
        logger.exception("Failed to log request history for location=%s", location)


@router.get("/weather", response_model=WeatherResponse)
async def get_weather(
    request: Request,
    background_tasks: BackgroundTasks,
    weather_request: WeatherRequest = Depends(),
    weather_service: WeatherService = Depends(get_weather_service),
):
    result = await weather_service.get_weather(weather_request)
    background_tasks.add_task(
        _log_request, request.app.state.db_session_factory, weather_request.location
    )
    return result


@router.post("/weather/batch", response_model=BatchWeatherResponse)
async def post_weather_batch(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    batch_request: BatchWeatherRequest,
    weather_service: WeatherService = Depends(get_weather_service),
    settings: Settings = Depends(get_settings),
):
    # The global check_rate_limit dependency already consumed 1 unit and
    # validated the key. Read it here from headers — no re-validation needed.
    key = request.headers.get("X-API-Key", "")
    # Global check_rate_limit already consumed 1 unit. This consumes N more.
    # Total cost for a batch of N is N+1 units.
    await check_batch_rate_limit(
        n=len(batch_request.locations),
        request=request,
        response=response,
        key=key,
        settings=settings,
    )
    result = await weather_service.get_weather_batch(batch_request.locations)
    for item in batch_request.locations:
        background_tasks.add_task(
            _log_request, request.app.state.db_session_factory, item.location
        )
    return result
