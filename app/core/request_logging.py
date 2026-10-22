import logging
import time
import uuid

from fastapi import FastAPI, Request

logger = logging.getLogger("taskhub.requests")


def register_request_logging(app: FastAPI) -> None:

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        request_id = str(uuid.uuid4())
        start = time.perf_counter()

        try:
            response = await call_next(request)

        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000

            logger.exception(
                "Request failed | id=%s | method=%s | path=%s | duration_ms=%.2f",
                request_id,
                request.method,
                request.url.path,
                duration_ms,
            )

            raise

        duration_ms = (time.perf_counter() - start) * 1000

        logger.info(
            "HTTP | id=%s | method=%s | path=%s | status=%s | duration_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )

        response.headers["X-Request-ID"] = request_id

        return response
