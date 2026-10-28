from app.core.error_messages import ErrorMessages


class AppException(Exception):
    def __init__(
        self,
        status_code: int,
        message: str,
        headers: dict[str, str] | None = None,
    ):
        self.status_code = status_code
        self.message = message
        self.headers = headers
        super().__init__(message)


class NotFoundException(AppException):
    def __init__(self, message: str):
        super().__init__(404, message)


class UnauthorizedException(AppException):
    def __init__(
        self,
        message: str = ErrorMessages.INVALID_CREDENTIALS,
    ):
        super().__init__(
            401,
            message,
            headers={"WWW-Authenticate": "Bearer"},
        )


class ForbiddenException(AppException):
    def __init__(
        self,
        message: str = ErrorMessages.FORBIDDEN,
    ):
        super().__init__(403, message)


class ConflictException(AppException):
    def __init__(self, message: str):
        super().__init__(409, message)


class ValidationException(AppException):
    def __init__(self, message: str = "Validation failed"):
        super().__init__(status_code=422, message=message)


class BadRequestException(AppException):
    def __init__(self, message: str = "Bad request"):
        super().__init__(status_code=400, message=message)
