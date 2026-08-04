"""Redis-backed cache and rate-limit store."""

from app.cache.client import close_redis, get_redis

__all__ = ["close_redis", "get_redis"]
