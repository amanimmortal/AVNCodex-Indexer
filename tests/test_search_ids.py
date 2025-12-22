import pytest
import asyncio
from sqlalchemy.future import select
from sqlalchemy import text
from app.models import Game
from app.services.game_service import GameService
from app.database import engine, init_db, AsyncSessionLocal


from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_search_filters():
    # 1. Initialize DB (Triggers Migration Logic)
    await init_db()

    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: None)  # Just ensure connected

    # 2. Setup Data
    async with AsyncSessionLocal() as session:
        # Clear existing
        await session.execute(text("DELETE FROM games"))

        now = datetime.now(timezone.utc)

        # Game 1: Type 14 (RenPy), Status 1 (Ongoing), Tags [4, 134] (3dcg, vaginal sex)
        g1 = Game(
            f95_id=1,
            name="RenPy Game",
            type_id=14,
            status_id=1,
            status="Ongoing",
            tags='["4", "134"]',
            details_json='{"type": 14, "status": 1, "tags": [4, 134]}',
            last_enriched=now,
            f95_last_update=now,
        )

        # Game 2: Type 19 (Unity), Status 1, Tags [4]
        g2 = Game(
            f95_id=2,
            name="Unity Game",
            type_id=19,
            status_id=1,
            status="Ongoing",
            tags='["4"]',
            details_json='{"type": 19, "status": 1, "tags": [4]}',
            last_enriched=now,
            f95_last_update=now,
        )

        # Game 3: Type 14, Status 1, Tags [4, 119] (Spanking included)
        g3 = Game(
            f95_id=3,
            name="Spanking Game",
            type_id=14,
            status_id=1,
            status="Ongoing",
            tags='["4", "119"]',
            details_json='{"type": 14, "status": 1, "tags": [4, 119]}',
            last_enriched=now,
            f95_last_update=now,
        )

        session.add_all([g1, g2, g3])
        await session.commit()

    # Verify Data
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Game))
        games = result.scalars().all()
        # Write to file
        with open("debug.log", "w") as f:
            f.write(f"DEBUG: Games in DB: {[g.name for g in games]}\n")
            for g in games:
                f.write(f"DEBUG: Game {g.f95_id}: type_id={g.type_id}, tags={g.tags}\n")

        # 3. Test Service Logic
        service = GameService(session)

        # Test A: Engine Filter (RenPy=14)
        print("DEBUG: Testing Engine=14")
        results = await service.search_and_index(engine=14)
        with open("debug.log", "a") as f:
            f.write(f"DEBUG: Test A Results: {[g.name for g in results]}\n")
        ids = [g.f95_id for g in results]
        assert 1 in ids
        assert 3 in ids
        assert 2 not in ids

        # Test B1: Exclude Empty List (Should be same as A)
        results = await service.search_and_index(engine=14, exclude_tags=[])
        with open("debug.log", "a") as f:
            f.write(f"DEBUG: Test B1 Results: {[g.name for g in results]}\n")
        assert len(results) == 2

        # Test B2: Exclude Tags (Exclude 119 - Spanking)
        results = await service.search_and_index(engine=14, exclude_tags=["119"])
        with open("debug.log", "a") as f:
            f.write(f"DEBUG: Test B2 Results: {[g.name for g in results]}\n")
        ids = [g.f95_id for g in results]
        assert 1 in ids
        assert 3 not in ids  # Has 119

        # Test C: Full Query (Engine 14, Status 1, Exclude 119)
        results = await service.search_and_index(
            engine=14, status="1", exclude_tags=["119"]
        )
        with open("debug.log", "a") as f:
            f.write(f"DEBUG: Test C Results: {[g.name for g in results]}\n")
        ids = [g.f95_id for g in results]
        assert 1 in ids
        assert len(ids) == 1

        print("\n\nALL SEARCH TESTS PASSED successfully!")
