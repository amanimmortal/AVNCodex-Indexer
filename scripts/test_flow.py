import asyncio
import logging
from app.database import init_db, engine
from app.services.game_service import GameService
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Game
from sqlalchemy.future import select

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    # Use a separate test DB to ensure clean state and avoid locks
    # We must RECREATE the engine because the global one matches the .env config
    from sqlmodel import create_engine
    from sqlalchemy.ext.asyncio import create_async_engine

    test_db_url = "sqlite+aiosqlite:///data/test_index_clean.db"

    # Clean previous run
    import os

    if os.path.exists("data/test_index_clean.db"):
        os.remove("data/test_index_clean.db")

    engine_test = create_async_engine(test_db_url, echo=False, future=True)

    # We need to hack/patch the module or just use this engine for our session
    # but init_db uses the global engine...
    # We will redefine init_db logic here.
    from sqlmodel import SQLModel

    async with engine_test.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    logger.info("Initialized CLEAN Test DB.")

    async_session = sessionmaker(
        engine_test, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        service = GameService(session)

        # 1. Test Hybrid Search (likely matching nothing locally first)
        query = "Eternum"
        logger.info(f"Searching for '{query}'...")
        games = await service.search_and_index(query)

        if games:
            logger.info(f"Found {len(games)} games:")
            for g in games:
                logger.info(f"- {g.name} (ID: {g.id}) - Source: {g.author}")
                logger.info(f"  Status: {g.status}")
                logger.info(f"  Last Update: {g.f95_last_update}")
                if g.details_json:
                    logger.info(f"  Details Length: {len(g.details_json)}")
                    # Preview check
                    import json

                    d = json.loads(g.details_json)
                    logger.info(f"  Details Keys: {list(d.keys())}")
        else:
            logger.error("No games found. Check F95Client/RSSClient?")

        # 2. Verify Persistence
        logger.info("Verifying persistence by fetching ID 1 again...")
        # Assuming we found something, let's pick the first one
        if games:
            test_id = games[0].id
            # Create NEW session to be sure
            async with async_session() as session2:
                service2 = GameService(session2)
                game_check = await service2.get_game_by_id(test_id)
                if game_check:
                    logger.info(f"Successfully retrieved from DB: {game_check.name}")
                else:
                    logger.error("Failed to retrieve game from DB after save!")

        # 3. Test Force Update
        if games:
            test_id = games[0].id
            logger.info(f"Force updating game ID {test_id}...")
            updated_game = await service.force_update_game(test_id)
            if updated_game:
                logger.info(
                    f"Force update result: {updated_game.name} v{updated_game.version}"
                )
                if updated_game.details_json:
                    logger.info("Details JSON present (F95Checker working).")
                else:
                    logger.info(
                        "No details JSON (Maybe F95Checker didn't have it or wasn't used)."
                    )


if __name__ == "__main__":
    asyncio.run(main())
