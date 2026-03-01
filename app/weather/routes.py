from fastapi import APIRouter, Depends
from app.config import get_settings, Settings
from app.weather.service import get_weather_service, WeatherService
from app.weather.schema import WeatherRequest, WeatherResponse

router = APIRouter(
    prefix="/v1",
    tags=["Weather"],
)

@router.get("/weather", response_model=WeatherResponse)
async def get_weather(request: WeatherRequest = Depends(), weather_service: WeatherService = Depends(get_weather_service)):
    return await weather_service.get_weather(request)


