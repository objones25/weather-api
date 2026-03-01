from fastapi import Depends, HTTPException, Security, Request, Response
from app.config import get_settings, Settings
from redis.asyncio.client import Redis
from app.auth import api_key_header
from uuid import uuid4
import time

async def check_rate_limit(request: Request, response: Response,key: str = Security(api_key_header), settings: Settings = Depends(get_settings)) -> None:
    redis: Redis = request.app.state.redis_client
    now = time.time()
    window_start = now - settings.rate_limit_window
    redis_key = f"rate_limit:{key}"
    await redis.zremrangebyscore(redis_key, "-inf", window_start)
    count = await redis.zcard(redis_key)
    oldest = await redis.zrange(redis_key, 0, 0, withscores=True)
    reset_time = (oldest[0][1] + settings.rate_limit_window) if oldest else (now + settings.rate_limit_window)
    response.headers["X-RateLimit-Remaining"] = str(max(settings.rate_limit_requests - count,0))
    response.headers["X-RateLimit-Reset"] = str(int(reset_time))
    response.headers["X-RateLimit-Limit"] = str(settings.rate_limit_requests) 
    if count >= settings.rate_limit_requests:
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
    await redis.zadd(redis_key, {str(uuid4()): now})
    await redis.expire(redis_key, settings.rate_limit_window)