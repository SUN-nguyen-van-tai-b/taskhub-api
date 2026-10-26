from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.exception_handlers import register_exception_handlers
from app.core.logging_config import setup_logging
from app.core.request_logging import register_request_logging
from app.db.redis import close_redis
from app.db.session import engine

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: không cần mở kết nối thủ công.
    yield

    # Shutdown: giải phóng tài nguyên.
    try:
        await close_redis()
    finally:
        await engine.dispose()


app = FastAPI(
    title="TaskHub API",
    version="1.0.0",
)

register_request_logging(app)
register_exception_handlers(app)

app.include_router(api_router)
