from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Literal

class Settings(BaseSettings):
    app_name: str = "Weather API"
    app_description: str = "Weather API wrapper with fastapi"
    app_version: str = "0.1.0"
    weather_api_key: str
    weather_api_url: str = "https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline"
    redis_host: str = "redis-17234.c16.us-east-1-2.ec2.cloud.redislabs.com"
    redis_port: int = 17234
    redis_username: str = "default"
    redis_password: str
    cache_ttl: int = 43200
    environment: Literal["development", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "DEBUG"
    api_key: str
    rate_limit_requests: int = 60
    rate_limit_window: int = 60


    model_config = SettingsConfigDict(env_file=".env")


@lru_cache
def get_settings() -> Settings:
    return Settings()