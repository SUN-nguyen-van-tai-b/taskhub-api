from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import CONFLICT, FORBIDDEN, UNAUTHORIZED, VALIDATION_ERROR
from app.core.enums import TokenType
from app.core.error_messages import ErrorMessages
from app.core.exceptions import (
    ConflictException,
    ForbiddenException,
    UnauthorizedException,
)
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.redis import get_redis
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    LogoutRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserLogin,
)
from app.schemas.user import UserCreate, UserResponse
from app.services.token_service import (
    consume_refresh_token,
    issue_token_pair,
    revoke_refresh_token,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=UserResponse,
    summary="Register a new user",
    responses={
        **CONFLICT,
        **VALIDATION_ERROR,
    },
)
async def register(
    user: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    existing_user = await db.scalar(select(User).where(User.email == user.email))

    if existing_user is not None:
        raise ConflictException(ErrorMessages.EMAIL_ALREADY_EXISTS)

    new_user = User(
        email=user.email,
        full_name=user.full_name,
        hashed_password=hash_password(user.password),
    )

    db.add(new_user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictException(ErrorMessages.EMAIL_ALREADY_EXISTS) from exc

    await db.refresh(new_user)

    return new_user


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and issue access/refresh tokens",
    responses={
        **UNAUTHORIZED,
        **FORBIDDEN,
        **VALIDATION_ERROR,
    },
)
async def login(
    credentials: UserLogin,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> TokenResponse:
    existing_user = await db.scalar(select(User).where(User.email == credentials.email))

    # User không tồn tại vẫn verify với dummy hash.
    password_hash = (
        existing_user.hashed_password
        if existing_user is not None
        else DUMMY_PASSWORD_HASH
    )

    is_valid = verify_password(
        credentials.password,
        password_hash,
    )

    if existing_user is None or not is_valid:
        raise UnauthorizedException(ErrorMessages.INVALID_CREDENTIALS)

    if not existing_user.is_active:
        raise ForbiddenException(ErrorMessages.ACCOUNT_INACTIVE)

    return await issue_token_pair(
        redis=redis,
        user_id=existing_user.id,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate refresh token",
    responses={
        **UNAUTHORIZED,
        **VALIDATION_ERROR,
    },
)
async def refresh_token(
    data: RefreshTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
):
    credentials_exception = UnauthorizedException(ErrorMessages.INVALID_REFRESH_TOKEN)

    try:
        payload = decode_token(data.refresh_token)
    except jwt.InvalidTokenError as exc:
        raise credentials_exception from exc

    if payload.get("type") != TokenType.REFRESH:
        raise credentials_exception

    user_id = payload.get("sub")
    jti = payload.get("jti")

    if (
        not isinstance(user_id, str)
        or not user_id.isdecimal()
        or not isinstance(jti, str)
        or not jti
    ):
        raise credentials_exception

    user = await db.get(User, int(user_id))

    if user is None or not user.is_active:
        raise credentials_exception

    stored_user_id = await consume_refresh_token(redis, jti)
    if stored_user_id != user_id:
        raise UnauthorizedException(ErrorMessages.REFRESH_TOKEN_REVOKED)

    return await issue_token_pair(
        redis=redis,
        user_id=user.id,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    data: LogoutRequest,
    redis: Annotated[Redis, Depends(get_redis)],
):
    credentials_exception = UnauthorizedException(ErrorMessages.INVALID_REFRESH_TOKEN)

    # 1. Decode Refresh Token
    try:
        payload = decode_token(data.refresh_token)
    except jwt.InvalidTokenError as exc:
        raise credentials_exception from exc

    # 2. Kiểm tra JWT có đúng TokenType.REFRESH.
    if payload.get("type") != TokenType.REFRESH:
        raise credentials_exception

    # 3. Kiểm tra jti hợp lệ
    jti = payload.get("jti")
    if not isinstance(jti, str) or not jti:
        raise credentials_exception

    # 4. Xóa Refresh Token trong Redis
    await revoke_refresh_token(redis, jti)

    # 5. Không trả response body
