from redis.asyncio import Redis


async def save_refresh_token(
    redis: Redis,
    jti: str,
    user_id: int,
) -> None:
    await redis.set(
        f"refresh:{jti}",
        str(user_id),
        ex=7 * 24 * 60 * 60,
    )


async def get_refresh_token(
    redis: Redis,
    jti: str,
) -> str | None:
    user_id = await redis.get(
        f"refresh:{jti}",
    )
    return user_id


async def revoke_refresh_token(
    redis: Redis,
    jti: str,
) -> None:
    await redis.delete(
        f"refresh:{jti}",
    )


async def consume_refresh_token(
    redis: Redis,
    jti: str,
) -> str | None:
    user_id = await redis.getdel(f"refresh:{jti}")
    return user_id
