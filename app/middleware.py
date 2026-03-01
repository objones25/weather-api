import time
import uuid
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)

class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time_ms = int((time.time() - start_time) * 1000)
        request_id = getattr(request.state, "request_id", None)
        logger.info(
            "%s %s %d %dms request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            process_time_ms,
            request_id,
        )
        response.headers["X-Process-Time"] = str(process_time_ms)
        return response

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response