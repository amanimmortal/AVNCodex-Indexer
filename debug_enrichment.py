import asyncio
import os
import sys

# Add app to path
sys.path.append(os.getcwd())

from app.database import AsyncSessionLocal
from app.models import Game
from sqlalchemy.future import select
from sqlalchemy import func


async def check_enrichment_metrics():
    async with AsyncSessionLocal() as session:
        # Check Total Games
        stmt_total = select(func.count(Game.f95_id))
        result = await session.execute(stmt_total)
        total = result.scalar()

        # Check Pending Enrichment
        stmt_pending = select(func.count(Game.f95_id)).where(
            Game.last_enriched.is_(None)
        )
        result = await session.execute(stmt_pending)
        pending = result.scalar()

        # Check 5 sample games with last_enriched = None
        stmt_sample = select(Game).where(Game.last_enriched.is_(None)).limit(5)
        result = await session.execute(stmt_sample)
        samples = result.scalars().all()

        print(f"Total Games: {total}")
        print(f"Pending Enrichment: {pending}")
        print(f"Sample IDs: {[g.f95_id for g in samples]}")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(check_enrichment_metrics())
