import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("taskhub.errors")


def register_exception_handlers(app: FastAPI) -> None:

    @app.exception_handler(Exception)
    async def unexpected_error_handler(
        request: Request,
        exc: Exception,
    ):
        # Ghi traceback để developer kiểm tra.
        logger.error(
            "Unhandled error | method=%s | path=%s",
            request.method,
            request.url.path,
            exc_info=(type(exc), exc, exc.__traceback__),
        )

        # Không đưa thông tin lỗi nội bộ cho frontend.
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
            },
        )
