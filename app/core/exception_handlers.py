import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.error_messages import ErrorMessages
from app.core.exceptions import AppException

logger = logging.getLogger("taskhub.errors")


def register_exception_handlers(app: FastAPI) -> None:

    # 1. Xử lý các lỗi nghiệp vụ.
    @app.exception_handler(AppException)
    async def app_error_handler(
        request: Request,
        exc: AppException,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
            headers=exc.headers,
        )

    # 2. Xử lý lỗi không mong muốn.
    @app.exception_handler(Exception)
    async def unexpected_error_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.error(
            "Unhandled error | method=%s | path=%s",
            request.method,
            request.url.path,
            exc_info=(type(exc), exc, exc.__traceback__),
        )

        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        errors = [
            {
                "field": ".".join(str(item) for item in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]

        return JSONResponse(
            status_code=422,
            content={
                "detail": ErrorMessages.VALIDATION_FAILED,
                "errors": errors,
            },
        )
