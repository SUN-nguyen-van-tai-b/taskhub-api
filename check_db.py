import asyncio

from sqlalchemy import text

from app.db.session import AsyncSessionLocal


async def main() -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("SELECT 1"))
        print(result.scalar_one())


if __name__ == "__main__":
    asyncio.run(main())