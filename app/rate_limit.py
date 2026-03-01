from fastapi import Depends, HTTPException, Security, Request
from app.config import get_settings, Settings
from redis.asyncio.client import Redis
from app.auth import api_key_header
from uuid import uuid4
import time

async def check_rate_limit(request: Request,key: str = Security(api_key_header), settings: Settings = Depends(get_settings)) -> None:
    redis: Redis = request.app.state.redis_client
    now = time.time()
    window_start = now - settings.rate_limit_window
    redis_key = f"rate_limit:{key}"
    await redis.zremrangebyscore(redis_key, "-inf", window_start)
    count = await redis.zcard(redis_key)
    if count >= settings.rate_limit_requests:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    await redis.zadd(redis_key, {str(uuid4()): now})
    await redis.expire(redis_key, settings.rate_limit_window)