from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from pwdlib import PasswordHash

from app.core.config import settings
from app.core.enums import TokenType

DUMMY_PASSWORD_HASH = "$argon2id$v=19$m=65536,t=3,p=4$dJg++zEwmdT2eoYRLygN5g$Mn44eLGN2MOvfT8da5KpjcwktlzXJoeEFJp1+uQmNMY"
password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hasher.verify(password, hashed_password)


def create_token(
    user_id: int,
    token_type: str,
) -> tuple[str, str]:
    if token_type == TokenType.ACCESS:
        expires_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
    elif token_type == TokenType.REFRESH:
        expires_minutes = settings.REFRESH_TOKEN_EXPIRE_MINUTES
    else:
        raise ValueError("Invalid token type")

    # 2. Tạo JTI duy nhất cho token.
    jti = str(uuid4())

    # 3. Tính thời gian hết hạn.
    expires_at = datetime.now(UTC) + timedelta(minutes=expires_minutes)

    # 4. Tạo JWT payload.
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "jti": jti,
        "exp": expires_at,
    }

    # 5. Ký JWT.
    token = jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    return token, jti


def decode_token(token: str) -> dict:
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
