import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_cache import redis_client
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check(
    db: Annotated[AsyncSession, Depends(get_db)],
):
    database_status = "up"
    redis_status = "up"

    # 1. Kiểm tra PostgreSQL
    try:
        # SELECT 1 là query đơn giản để kiểm tra kết nối.
        await db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        database_status = "down"
        logger.exception("Database health check failed")

    # 2. Kiểm tra Redis
    try:
        await redis_client.ping()
    except (RedisError, OSError):
        redis_status = "down"
        logger.exception("Redis health check failed")

    # 3. Tổng hợp kết quả
    healthy = database_status == "up" and redis_status == "up"

    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "healthy" if healthy else "unhealthy",
            "services": {
                "database": database_status,
                "redis": redis_status,
            },
        },
    )
