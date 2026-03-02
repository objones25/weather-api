import time
import uuid
import logging
from starlette.types import ASGIApp, Scope, Receive, Send, Message
from starlette.datastructures import MutableHeaders
from app.metrics import HTTP_REQUESTS_TOTAL, HTTP_REQUEST_DURATION_SECONDS

logger = logging.getLogger(__name__)


class TimingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                MutableHeaders(scope=message).append("X-Process-Time", str(elapsed_ms))
            await send(message)

        await self.app(scope, receive, send_wrapper)

        duration = time.perf_counter() - start
        total_ms = int(duration * 1000)
        path = scope.get("path", "")
        request_id = scope.get("state", {}).get("request_id")
        logger.info(
            "%s %s %d %dms request_id=%s",
            scope.get("method", ""),
            path,
            status_code,
            total_ms,
            request_id,
        )

        if path != "/metrics":
            HTTP_REQUESTS_TOTAL.labels(
                method=scope.get("method", ""),
                path=path,
                status_code=str(status_code),
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=scope.get("method", ""),
                path=path,
            ).observe(duration)


class RequestIDMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).append("X-Request-ID", request_id)
            await send(message)

        await self.app(scope, receive, send_wrapper)
