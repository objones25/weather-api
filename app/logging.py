import logging
import logging.config
from app.config import Settings


def setup_logging(settings: Settings) -> None:
    formatter = "dev" if settings.environment == "development" else "json"

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "dev": {
                "format": "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "json": {
                "()": "pythonjsonlogger.json.JsonFormatter",
                "format": "%(asctime)s %(levelname)s %(name)s %(lineno)d %(message)s",
            },
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": formatter,
            },
        },
        "loggers": {
            "uvicorn":   {"level": "WARNING", "propagate": False},
            "httpx":     {"level": "WARNING", "propagate": False},
            "httpcore":  {"level": "WARNING", "propagate": False},
            "redis":     {"level": "WARNING", "propagate": False},
        },
        "root": {
            "level": settings.log_level,
            "handlers": ["default"],
        },
    }

    logging.config.dictConfig(config)
