from pydantic import BaseModel, field_validator
from app.weather.schema import WeatherRequest


class CacheWarmRequest(BaseModel):
    locations: list[WeatherRequest]

    @field_validator("locations")
    @classmethod
    def validate_size(cls, v: list[WeatherRequest]) -> list[WeatherRequest]:
        if len(v) == 0:
            raise ValueError("locations must contain at least one request")
        if len(v) > 50:
            raise ValueError("locations must contain at most 50 requests")
        return v


class CacheWarmError(BaseModel):
    location: str
    detail: str


class CacheWarmResponse(BaseModel):
    total: int
    succeeded: int
    failed: int
    errors: list[CacheWarmError]
