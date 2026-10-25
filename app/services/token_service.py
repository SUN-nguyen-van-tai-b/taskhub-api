from redis.asyncio import Redis

REFRESH_TTL = 7 * 24 * 60 * 60


def user_refresh_key(user_id: int) -> str:
    return f"user_refresh_tokens:{user_id}"


async def save_refresh_token(
    redis: Redis,
    jti: str,
    user_id: int,
) -> None:
    user_key = user_refresh_key(user_id)

    async with redis.pipeline(transaction=True) as pipe:
        pipe.set(f"refresh:{jti}", str(user_id), ex=REFRESH_TTL)
        pipe.sadd(user_key, jti)
        pipe.expire(user_key, REFRESH_TTL)
        await pipe.execute()


async def get_refresh_token(
    redis: Redis,
    jti: str,
) -> str | None:
    return await redis.get(f"refresh:{jti}")


async def revoke_refresh_token(
    redis: Redis,
    jti: str,
) -> None:
    # Lấy user_id trước khi xóa token.
    user_id = await get_refresh_token(redis, jti)

    if user_id is None:
        return

    async with redis.pipeline(transaction=True) as pipe:
        pipe.delete(f"refresh:{jti}")
        pipe.srem(user_refresh_key(int(user_id)), jti)
        await pipe.execute()


async def consume_refresh_token(
    redis: Redis,
    jti: str,
) -> str | None:
    # GETDEL bảo đảm một refresh token chỉ được sử dụng một lần.
    user_id = await redis.getdel(f"refresh:{jti}")

    if user_id is not None:
        await redis.srem(
            user_refresh_key(int(user_id)),
            jti,
        )

    return user_id


async def revoke_all_refresh_tokens(
    redis: Redis,
    user_id: int,
) -> None:
    user_key = user_refresh_key(user_id)

    # Lấy tất cả JTI thuộc user.
    jtis = await redis.smembers(user_key)

    async with redis.pipeline(transaction=True) as pipe:
        for jti in jtis:
            pipe.delete(f"refresh:{jti}")

        pipe.delete(user_key)
        await pipe.execute()
