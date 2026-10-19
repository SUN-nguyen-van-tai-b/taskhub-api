from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hasher.verify(password, hashed_password)


def create_token(
    user_id: int,
    token_type: str,
    expires_minutes: int,
) -> str:
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "jti": str(uuid4()),
        "exp": datetime.now(UTC) + timedelta(minutes=expires_minutes),
    }

    return jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm="HS256",
    )


def decode_token(token: str) -> dict:
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=["HS256"],
        options={"require": ["sub", "exp", "jti", "type"]},
    )
