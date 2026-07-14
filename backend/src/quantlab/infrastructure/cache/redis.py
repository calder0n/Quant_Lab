"""Factory for the async Redis client. Lifecycle is owned by the composition root."""

from redis.asyncio import Redis

from quantlab.config import Settings


def create_redis(settings: Settings) -> Redis:
    """Build an async Redis client from configuration (connects lazily)."""
    return Redis.from_url(settings.redis_url, decode_responses=True)
