from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_token, decode_token, hash_password, verify_password
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
    revoke_refresh_token,
    save_refresh_token,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=UserResponse,
)
async def register(
    user: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    query = select(User).where(User.email == user.email)
    result = await db.scalars(query)
    existing_user = result.first()

    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already exists"
        )

    new_user = User(
        email=user.email,
        full_name=user.full_name,
        hashed_password=hash_password(user.password),
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return new_user


@router.post(
    "/login",
    response_model=TokenResponse,
)
async def login(
    credentials: UserLogin,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
):
    query = select(User).where(User.email == credentials.email)
    result = await db.scalars(query)
    existing_user = result.first()

    if existing_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    is_valid = verify_password(credentials.password, existing_user.hashed_password)

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    if not existing_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive"
        )

    access_token = create_token(
        user_id=existing_user.id, token_type="access", expires_minutes=30
    )
    refresh_token = create_token(
        user_id=existing_user.id, token_type="refresh", expires_minutes=7 * 24 * 60
    )

    payload = decode_token(refresh_token)
    jti = payload["jti"]

    await save_refresh_token(redis, jti, existing_user.id)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.post(
    "/refresh",
    response_model=TokenResponse,
)
async def refresh_token(
    data: RefreshTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(
            data.refresh_token,
        )

        if payload.get("type") != "refresh":
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
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token revoked or expired",
            )

    except (jwt.InvalidTokenError, ValueError, TypeError) as exc:
        raise credentials_exception from exc

    # Tạo Access Token mới
    new_access_token = create_token(
        user_id=user.id,
        token_type="access",
        expires_minutes=30,
    )

    # Tạo Refresh Token mới
    new_refresh_token = create_token(
        user_id=user.id,
        token_type="refresh",
        expires_minutes=7 * 24 * 60,
    )

    # Lấy jti của Refresh Token mới
    new_payload = decode_token(new_refresh_token)
    new_jti = new_payload["jti"]

    # Lưu Refresh Token mới vào Redis
    await save_refresh_token(redis, new_jti, user.id)

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    data: LogoutRequest,
    redis: Annotated[Redis, Depends(get_redis)],
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 1. Decode Refresh Token
    try:
        payload = decode_token(data.refresh_token)
    except jwt.InvalidTokenError as exc:
        raise credentials_exception from exc

    # 2. Kiểm tra type == "refresh"
    if payload.get("type") != "refresh":
        raise credentials_exception

    # 3. Kiểm tra jti hợp lệ
    jti = payload.get("jti")
    if not isinstance(jti, str) or not jti:
        raise credentials_exception

    # 4. Xóa Refresh Token trong Redis
    await revoke_refresh_token(redis, jti)

    # 5. Không trả response body
