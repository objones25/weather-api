from fastapi import Depends, HTTPException, Security, Request, Response
from app.config import get_settings, Settings
from app.metrics import RATE_LIMIT_REJECTIONS_TOTAL
from redis.asyncio.client import Redis
from app.auth import api_key_header
from uuid import uuid4
import time

async def check_rate_limit(request: Request, response: Response,key: str = Security(api_key_header), settings: Settings = Depends(get_settings)) -> None:
    redis: Redis = request.app.state.redis_client
    now = time.time()
    window_start = now - settings.rate_limit_window
    redis_key = f"rate_limit:{key}"
    # Pipeline 1: evict expired entries, count remaining, fetch oldest for reset time
    async with redis.pipeline(transaction=False) as pipe:
        pipe.zremrangebyscore(redis_key, "-inf", window_start)
        pipe.zcard(redis_key)
        pipe.zrange(redis_key, 0, 0, withscores=True)
        _, count, oldest = await pipe.execute()

    reset_time = (oldest[0][1] + settings.rate_limit_window) if oldest else (now + settings.rate_limit_window)
    response.headers["X-RateLimit-Limit"] = str(settings.rate_limit_requests)
    response.headers["X-RateLimit-Remaining"] = str(max(settings.rate_limit_requests - count, 0))
    response.headers["X-RateLimit-Reset"] = str(int(reset_time))

    if count >= settings.rate_limit_requests:
        RATE_LIMIT_REJECTIONS_TOTAL.inc()
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={
                "Retry-After": str(int(reset_time - now)),
                "X-RateLimit-Limit": str(settings.rate_limit_requests),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(reset_time)),
            },
        )

    # Pipeline 2: record this request and refresh TTL
    async with redis.pipeline(transaction=False) as pipe:
        pipe.zadd(redis_key, {str(uuid4()): now})
        pipe.expire(redis_key, settings.rate_limit_window)
        await pipe.execute()