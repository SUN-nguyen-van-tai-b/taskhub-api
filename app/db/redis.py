from collections.abc import AsyncGenerator

from redis.asyncio import Redis

from app.core.config import settings

redis_client = Redis.from_url(
    settings.REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=1,
    socket_timeout=1,
)


async def get_redis() -> AsyncGenerator[Redis]:
    yield redis_client


async def close_redis() -> None:
    await redis_client.aclose()
