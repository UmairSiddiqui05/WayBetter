"""Redis client factory.

Redis backs candidate/route caching and the per-IP + per-session rate limiter
(N-05). The limiter itself is A3's; this module only owns the connection.
"""

from __future__ import annotations

from functools import lru_cache

from redis.asyncio import Redis

from app.config import get_settings


@lru_cache(maxsize=1)
def get_redis() -> Redis:
    settings = get_settings()
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=settings.probe_timeout_seconds,
        socket_timeout=settings.probe_timeout_seconds,
    )


async def close_redis() -> None:
    """Close the connection pool on shutdown."""
    if get_redis.cache_info().currsize:
        await get_redis().aclose()
