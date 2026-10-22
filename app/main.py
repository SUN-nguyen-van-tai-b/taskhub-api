from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.exception_handlers import register_exception_handlers
from app.core.logging_config import setup_logging
from app.core.request_logging import register_request_logging

setup_logging()

app = FastAPI(
    title="TaskHub API",
    version="1.0.0",
)

register_request_logging(app)
register_exception_handlers(app)

app.include_router(api_router)
