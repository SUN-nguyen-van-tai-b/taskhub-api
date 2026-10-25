import json
import logging

from redis.exceptions import RedisError

from app.db.redis import redis_client

logger = logging.getLogger(__name__)

TASK_CACHE_TTL = 60  # 60 giây


async def get_task_cache_version(project_id: int) -> str | None:
    """
    Lấy phiên bản cache của Project.

    Khi Task thay đổi, tăng version.
    Các cache key cũ sẽ không được đọc nữa.
    """
    try:
        key = f"taskhub:tasks:version:{project_id}"
        return await redis_client.get(key) or "0"
    except RedisError:
        logger.warning("Redis cache unavailable", exc_info=True)
        return None


async def invalidate_task_cache(project_id: int) -> None:
    """
    Gọi sau khi tạo/sửa/xóa Task thành công.
    """
    key = f"taskhub:tasks:version:{project_id}"

    # Với Redis version keys, không tự ý xóa key này.
    # Xóa version sẽ có nguy cơ dùng lại version cũ.
    try:
        await redis_client.incr(key)
    except RedisError:
        logger.warning("Failed to invalidate task cache", exc_info=True)


async def read_task_cache(key: str) -> dict | None:
    try:
        cached = await redis_client.get(key)

        if cached is None:
            return None

        return json.loads(cached)

    except (RedisError, ValueError, TypeError):
        logger.warning("Failed to read task cache", exc_info=True)
        return None


async def write_task_cache(key: str, data: dict) -> None:
    try:
        await redis_client.set(
            key,
            json.dumps(data),
            ex=TASK_CACHE_TTL,
        )

    except (RedisError, ValueError, TypeError):
        logger.warning("Failed to write task cache", exc_info=True)


async def close_redis() -> None:
    await redis_client.aclose()
