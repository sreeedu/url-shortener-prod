import redis.asyncio as aioredis
from app.core.config import settings
from typing import Optional
import logging

logger = logging.getLogger(__name__)

redis_client: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global redis_client
    if redis_client is None:
        redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            # Background health check every 30s — no need to ping on every request
            health_check_interval=30,
            max_connections=50,
        )
    return redis_client


async def get_redis_or_none() -> Optional[aioredis.Redis]:
    """
    Returns Redis client if reachable, None if unavailable.
    Callers fall through to Postgres — app stays alive under Redis failure.

    Does NOT ping on every call — health_check_interval=30 handles background
    monitoring. Pinging on every redirect added a full extra round-trip to the
    hottest path in the system.
    """
    try:
        return await get_redis()
    except Exception as e:
        logger.warning(f"Redis unavailable: {e}. Falling back to Postgres.")
        return None


async def close_redis():
    global redis_client
    if redis_client:
        await redis_client.aclose()
        redis_client = None


def url_cache_key(short_code: str) -> str:
    return f"url:{short_code}"


def url_id_cache_key(short_code: str) -> str:
    return f"url_id:{short_code}"
