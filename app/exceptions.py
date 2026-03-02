from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi import Request
import logging

logger = logging.getLogger(__name__)


async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    log = logger.error if exc.status_code >= 500 else logger.warning
    log(
        "%s %s %d - %s",
        request.method,
        request.url.path,
        exc.status_code,
        exc.detail,
    )
    return await http_exception_handler(request, exc)


async def custom_validation_exception_handler(
    request: Request, exc: RequestValidationError
):
    logger.warning(
        "%s %s 422 - %s",
        request.method,
        request.url.path,
        exc.errors(),
    )
    return await request_validation_exception_handler(request, exc)
