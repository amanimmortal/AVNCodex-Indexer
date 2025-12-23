import asyncio
from app.database import AsyncSessionLocal
from app.models import Game
from sqlalchemy import func, select, cast, Integer


async def main():
    async with AsyncSessionLocal() as session:
        # Calculate C (Average Rating)
        stmt = select(func.avg(Game.rating)).where(Game.rating.isnot(None))
        result = await session.execute(stmt)
        avg_rating = result.scalar() or 0.0

        # Calculate quantile for m (e.g., 50th percentile of likes)
        # SQLite doesn't have percentile_cont easily, so let's just get average likes or count distribution
        stmt = select(func.avg(Game.likes)).where(Game.likes.isnot(None))
        result = await session.execute(stmt)
        avg_likes = result.scalar() or 0

        # Get count
        stmt = select(func.count(Game.f95_id))
        count = (await session.execute(stmt)).scalar()

        print(f"Count: {count}")
        print(f"Avg Rating (C): {avg_rating}")
        print(f"Avg Likes: {avg_likes}")

        # Get a distribution of likes to pick m
        # Select likes, count ordered by likes
        # This is strictly exploratory
        stmt = (
            select(Game.likes)
            .where(Game.likes.isnot(None))
            .order_by(Game.likes.desc())
            .limit(20)
        )
        top_likes = (await session.execute(stmt)).scalars().all()
        print(f"Top 20 likes: {top_likes}")


if __name__ == "__main__":
    asyncio.run(main())
