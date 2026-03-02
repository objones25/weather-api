import logging
from fastapi import APIRouter, Depends, BackgroundTasks, Request
from app.weather.service import get_weather_service, WeatherService
from app.weather.schema import WeatherRequest, WeatherResponse
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
