from redis.asyncio import Redis

from app.core.config import settings
from app.core.enums import TokenType
from app.core.security import create_token
from app.schemas.auth import TokenResponse

# TTL dùng chung với JWT Refresh Token.
REFRESH_TOKEN_TTL_SECONDS = settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60


def user_refresh_key(user_id: int) -> str:
    return f"user_refresh_tokens:{user_id}"


def refresh_key(jti: str) -> str:
    return f"refresh:{jti}"


async def save_refresh_token(
    redis: Redis,
    jti: str,
    user_id: int,
) -> None:
    user_key = user_refresh_key(user_id)

    # Lưu token và JTI theo user trong cùng transaction.
    async with redis.pipeline(transaction=True) as pipe:
        pipe.set(
            refresh_key(jti),
            str(user_id),
            ex=REFRESH_TOKEN_TTL_SECONDS,
        )

        pipe.sadd(user_key, jti)

        pipe.expire(
            user_key,
            REFRESH_TOKEN_TTL_SECONDS,
        )

        await pipe.execute()


REVOKE_ONE_SCRIPT = """
local user_id = redis.call('GET', KEYS[1])

if not user_id then
    return 0
end

redis.call('DEL', KEYS[1])
redis.call('SREM', 'user_refresh_tokens:' .. user_id, ARGV[1])

return 1
"""


async def revoke_refresh_token(
    redis: Redis,
    jti: str,
) -> None:
    # Xóa token và loại JTI khỏi Set cùng một thao tác.
    await redis.eval(
        REVOKE_ONE_SCRIPT,
        1,
        refresh_key(jti),
        jti,
    )


CONSUME_SCRIPT = """
local user_id = redis.call('GET', KEYS[1])

if not user_id then
    return nil
end

redis.call('DEL', KEYS[1])
redis.call('SREM', 'user_refresh_tokens:' .. user_id, ARGV[1])

return user_id
"""


async def consume_refresh_token(
    redis: Redis,
    jti: str,
) -> str | None:
    # Chỉ một request có thể consume thành công cùng JTI.
    return await redis.eval(
        CONSUME_SCRIPT,
        1,
        refresh_key(jti),
        jti,
    )


REVOKE_ALL_SCRIPT = """
local jtis = redis.call('SMEMBERS', KEYS[1])

for _, jti in ipairs(jtis) do
    redis.call('DEL', 'refresh:' .. jti)
end

redis.call('DEL', KEYS[1])

return #jtis
"""


async def revoke_all_refresh_tokens(
    redis: Redis,
    user_id: int,
) -> None:
    # Thu hồi tất cả token có trong Set tại thời điểm chạy.
    await redis.eval(
        REVOKE_ALL_SCRIPT,
        1,
        user_refresh_key(user_id),
    )


async def issue_token_pair(
    redis: Redis,
    user_id: int,
) -> TokenResponse:
    # Tạo Access Token.
    access_token, _ = create_token(
        user_id=user_id,
        token_type=TokenType.ACCESS,
    )

    # Tạo Refresh Token, lấy JTI trực tiếp.
    refresh_token, jti = create_token(
        user_id=user_id,
        token_type=TokenType.REFRESH,
    )

    # Lưu Refresh Token trong Redis.
    await save_refresh_token(
        redis=redis,
        jti=jti,
        user_id=user_id,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )
