import json
from typing import Any, Awaitable, Callable

import redis.asyncio as aioredis

from app.core.config import settings

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def with_cache(key: str, producer: Callable[[], Awaitable[Any]], ttl: int | None = None) -> Any:
    """Cache-aside: thử Redis trước, miss thì gọi producer rồi SETEX."""
    r = get_redis()
    full_key = f"cache:{key}"
    try:
        hit = await r.get(full_key)
        if hit is not None:
            return json.loads(hit)
    except Exception:
        pass  # Redis chết không được làm chết API
    value = await producer()
    try:
        await r.setex(full_key, ttl or settings.cache_ttl_seconds, json.dumps(value, default=str))
    except Exception:
        pass
    return value


async def invalidate_all() -> int:
    r = get_redis()
    n = 0
    async for k in r.scan_iter("cache:*", count=500):
        await r.delete(k)
        n += 1
    return n


async def acquire_pipeline_lock(ttl: int = 7200) -> bool:
    return bool(await get_redis().set("pipeline:lock", "1", nx=True, ex=ttl))


async def release_pipeline_lock() -> None:
    await get_redis().delete("pipeline:lock")
