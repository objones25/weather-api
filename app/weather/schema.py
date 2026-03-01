from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums – values taken directly from the Visual Crossing API docs
# ---------------------------------------------------------------------------

class UnitGroup(str, Enum):
    US = "us"
    UK = "uk"
    METRIC = "metric"
    BASE = "base"


class Language(str, Enum):
    ARABIC = "ar"
    BULGARIAN = "bg"
    CZECH = "cs"
    DANISH = "da"
    GERMAN = "de"
    GREEK = "el"
    ENGLISH = "en"
    SPANISH = "es"
    FARSI = "fa"
    FINNISH = "fi"
    FRENCH = "fr"
    HEBREW = "he"
    HUNGARIAN = "hu"
    ITALIAN = "it"
    JAPANESE = "ja"
    KOREAN = "ko"
    DUTCH = "nl"
    POLISH = "pl"
    PORTUGUESE = "pt"
    RUSSIAN = "ru"
    SLOVAKIAN = "sk"
    SERBIAN = "sr"
    SWEDISH = "sv"
    TURKISH = "tr"
    UKRAINIAN = "uk"
    VIETNAMESE = "vi"
    CHINESE = "zh"
    RAW_IDS = "id"  # returns raw descriptor IDs instead of translated strings


class IncludeOption(str, Enum):
    DAYS = "days"
    HOURS = "hours"
    MINUTES = "minutes"
    ALERTS = "alerts"
    CURRENT = "current"
    EVENTS = "events"
    OBS = "obs"
    REMOTE = "remote"
    FCST = "fcst"
    STATS = "stats"
    STATS_FCST = "statsfcst"


class Element(str, Enum):
    """
    Standard response elements listed in the Visual Crossing API docs.

    NOTE: The docs also mention unlisted "industry elements" (solar, marine,
    agriculture) that require a specific account license. Those are NOT
    included here. The field_validator on WeatherRequest.elements allows
    them through via the add:/remove: prefix path rather than blocking them.
    """
    CLOUDCOVER = "cloudcover"
    CONDITIONS = "conditions"
    DESCRIPTION = "description"
    DATETIME = "datetime"
    DATETIME_EPOCH = "datetimeEpoch"
    TZ_OFFSET = "tzoffset"
    DEW = "dew"
    FEELSLIKE = "feelslike"
    FEELSLIKE_MAX = "feelslikemax"
    FEELSLIKE_MIN = "feelslikemin"
    HUMIDITY = "humidity"
    ICON = "icon"
    MOON_PHASE = "moonphase"
    NORMAL = "normal"
    OFFSET_SECONDS = "offsetseconds"
    PRECIP = "precip"
    PRECIP_REMOTE = "precipremote"
    PRECIP_COVER = "precipcover"
    PRECIP_PROB = "precipprob"
    PRECIP_TYPE = "preciptype"
    PRESSURE = "pressure"
    SNOW = "snow"
    SNOW_DEPTH = "snowdepth"
    SOURCE = "source"
    STATIONS = "stations"
    SUNRISE = "sunrise"
    SUNRISE_EPOCH = "sunriseEpoch"
    SUNSET = "sunset"
    SUNSET_EPOCH = "sunsetEpoch"
    MOON_RISE = "moonrise"
    MOON_RISE_EPOCH = "moonriseEpoch"
    MOON_SET = "moonset"
    MOON_SET_EPOCH = "moonsetEpoch"
    TEMP = "temp"
    TEMP_MAX = "tempmax"
    TEMP_MIN = "tempmin"
    UV_INDEX = "uvindex"
    UV_INDEX2 = "uvindex2"
    VISIBILITY = "visibility"
    WIND_DIR = "winddir"
    WIND_GUST = "windgust"
    WIND_SPEED = "windspeed"
    WIND_SPEED_MAX = "windspeedmax"
    WIND_SPEED_MEAN = "windspeedmean"
    WIND_SPEED_MIN = "windspeedmin"
    SOLAR_RADIATION = "solarradiation"
    SOLAR_ENERGY = "solarenergy"
    SEVERE_RISK = "severerisk"
    CAPE = "cape"
    CIN = "cin"
    DEGREE_DAYS = "degreedays"
    ACC_DEGREE_DAYS = "accdegreedays"


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class WeatherRequest(BaseModel):
    location: str
    # date1/date2 stay as str: the API accepts ISO dates (yyyy-MM-dd),
    # UNIX timestamps, datetime strings (yyyy-MM-ddTHH:mm:ss), and dynamic
    # keywords like "today", "yesterday", "last30days" — too varied to enum.
    date1: str | None = None
    date2: str | None = None
    unit_group: UnitGroup = UnitGroup.US
    include: list[IncludeOption] | None = None
    # elements stays as list[str] because the API supports add:/remove: prefixes
    # (e.g. "add:aqius,remove:windgust") and unlisted industry elements.
    # The validator below checks the element name after stripping any prefix.
    elements: list[str] | None = None
    lang: Language = Language.ENGLISH

    @field_validator("elements")
    @classmethod
    def validate_elements(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        valid = {e.value for e in Element}
        for item in v:
            name = item.removeprefix("add:").removeprefix("remove:")
            if name not in valid:
                raise ValueError(
                    f"'{name}' is not a recognised element. "
                    f"If this is an industry element (solar/marine/agriculture), "
                    f"it may still be valid on your account but is not in the "
                    f"standard documented list."
                )
        return v
    
    @field_validator("location")
    @classmethod
    def validate_location(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("location cannot be empty")
        return v

    @model_validator(mode="after")
    def check_date2_requires_date1(self) -> WeatherRequest:
        if self.date2 and not self.date1:
            raise ValueError("date2 requires date1 to be set")
        return self


# ---------------------------------------------------------------------------
# Response – inner objects (bottom-up so forward refs aren't needed)
# ---------------------------------------------------------------------------

class HourlyWeather(BaseModel):
    datetime: str
    datetimeEpoch: int | None = None
    temp: float | None = None
    feelslike: float | None = None
    humidity: float | None = None
    dew: float | None = None
    precip: float | None = None
    precipprob: float | None = None
    preciptype: list[str] | None = None
    snow: float | None = None
    snowdepth: float | None = None
    windgust: float | None = None
    windspeed: float | None = None
    winddir: float | None = None
    pressure: float | None = None
    cloudcover: float | None = None
    visibility: float | None = None
    solarradiation: float | None = None
    solarenergy: float | None = None
    uvindex: float | None = None
    conditions: str | None = None
    icon: str | None = None
    source: str | None = None
    stations: list[str] | None = None


class DailyWeather(BaseModel):
    datetime: str
    datetimeEpoch: int | None = None
    tempmax: float | None = None
    tempmin: float | None = None
    temp: float | None = None
    feelslikemax: float | None = None
    feelslikemin: float | None = None
    feelslike: float | None = None
    dew: float | None = None
    humidity: float | None = None
    precip: float | None = None
    precipprob: float | None = None
    precipcover: float | None = None
    preciptype: list[str] | None = None
    snow: float | None = None
    snowdepth: float | None = None
    windgust: float | None = None
    windspeed: float | None = None
    winddir: float | None = None
    pressure: float | None = None
    cloudcover: float | None = None
    visibility: float | None = None
    uvindex: float | None = None
    severerisk: float | None = None
    sunrise: str | None = None
    sunriseEpoch: int | None = None
    sunset: str | None = None
    sunsetEpoch: int | None = None
    moonphase: float | None = None
    conditions: str | None = None
    description: str | None = None
    icon: str | None = None
    source: str | None = None
    stations: list[str] | None = None
    hours: list[HourlyWeather] | None = None


class WeatherStation(BaseModel):
    name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    distance: float | None = None
    usecount: int | None = None
    id: str | None = None
    contribution: float | None = None
    quality: int | None = None


class WeatherAlert(BaseModel):
    event: str | None = None
    headline: str | None = None
    ends: str | None = None
    endsEpoch: int | None = None
    onset: str | None = None
    onsetEpoch: int | None = None
    id: str | None = None
    language: str | None = None
    link: str | None = None
    description: str | None = None


class CurrentConditions(BaseModel):
    datetime: str
    datetimeEpoch: int | None = None
    temp: float | None = None
    feelslike: float | None = None
    humidity: float | None = None
    dew: float | None = None
    precip: float | None = None
    precipprob: float | None = None
    preciptype: list[str] | None = None
    snow: float | None = None
    snowdepth: float | None = None
    windgust: float | None = None
    windspeed: float | None = None
    winddir: float | None = None
    pressure: float | None = None
    cloudcover: float | None = None
    visibility: float | None = None
    solarradiation: float | None = None
    solarenergy: float | None = None
    uvindex: float | None = None
    sunrise: str | None = None
    sunriseEpoch: int | None = None
    sunset: str | None = None
    sunsetEpoch: int | None = None
    moonphase: float | None = None
    conditions: str | None = None
    icon: str | None = None
    source: str | None = None
    stations: list[str] | None = None


# ---------------------------------------------------------------------------
# Response – top-level
# ---------------------------------------------------------------------------

class WeatherResponse(BaseModel):
    queryCost: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    resolvedAddress: str | None = None
    address: str | None = None
    timezone: str | None = None
    tzoffset: float | None = None
    description: str | None = None
    days: list[DailyWeather] = []
    alerts: list[WeatherAlert] = []
    currentConditions: CurrentConditions | None = None
    stations: dict[str, WeatherStation] | None = None
