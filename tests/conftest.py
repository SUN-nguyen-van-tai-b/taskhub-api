import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from dotenv import load_dotenv
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

# Đọc .env trước khi import app.
load_dotenv()

TEST_DATABASE_URL = os.environ["TEST_DATABASE_URL"]
TEST_REDIS_URL = os.environ["TEST_REDIS_URL"]

# Bắt buộc dùng database test.
if not TEST_DATABASE_URL.endswith("/taskhub_test"):
    raise RuntimeError("Tests must use taskhub_test")

if not TEST_REDIS_URL.endswith("/1"):
    raise RuntimeError("Tests must use Redis database 1")

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["REDIS_URL"] = TEST_REDIS_URL

from app.db.redis import get_redis  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    # Tạo Engine mới cho mỗi test.
    # NullPool tránh tái sử dụng connection giữa các event loop.
    test_engine = create_async_engine(
        TEST_DATABASE_URL,
        poolclass=NullPool,
    )

    TestSession = async_sessionmaker(
        bind=test_engine,
        expire_on_commit=False,
    )

    test_redis = Redis.from_url(
        TEST_REDIS_URL,
        decode_responses=True,
    )

    async def override_db():
        async with TestSession() as session:
            yield session

    async def override_redis():
        yield test_redis

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_redis] = override_redis

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()

        await test_redis.aclose()
        await test_engine.dispose()
