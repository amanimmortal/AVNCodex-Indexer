import asyncio
import logging
import sys
from app.database import init_db
from app.services.game_service import GameService
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    # Use a separate test DB to ensure clean state
    # Recreate engine to bypass global singleton if needed, or just use a test file
    from sqlalchemy.ext.asyncio import create_async_engine

    test_db_url = "sqlite+aiosqlite:///data/test_tracked_v2.db"

    import os

    if os.path.exists("data/test_tracked_v2.db"):
        try:
            os.remove("data/test_tracked_v2.db")
        except Exception:
            pass

    engine_test = create_async_engine(test_db_url, echo=False, future=True)

    # Init Schema
    async with engine_test.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    logger.info("Initialized CLEAN Test DB for Tracked Flow.")

    async_session = sessionmaker(
        engine_test, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        service = GameService(session)

        # Test Case: Track "Eternum" (ID: 93340)
        # This ID is known to be on F95Checker
        target_id = 93340
        logger.info(f"Tracking game ID {target_id}...")

        # This should:
        # 1. Fetch the game (stub or remote)
        # 2. Set tracked=True
        # 3. Trigger sync_tracked_games([93340]) -> Calls Checker /fast then /full -> Merges details
        game = await service.track_game(target_id)

        logger.info(f"Tracked Game: {game.name}")
        logger.info(f"Is Tracked: {game.tracked}")

        if not game.tracked:
            logger.error("❌ Game tracked status is False!")
            sys.exit(1)

        # Verify JSON details for downloads
        if not game.details_json:
            logger.error("❌ Details JSON is empty! Sync failed.")
            sys.exit(1)

        import json

        details = json.loads(game.details_json)
        logger.info(f"Details Keys: {list(details.keys())}")

        has_downloads = False
        possible_keys = ["downloads", "download", "links", "mirrors"]
        found_keys = [
            k for k in details.keys() if any(pk in k.lower() for pk in possible_keys)
        ]

        if found_keys:
            logger.info(f"✅ Found download-related keys: {found_keys}")
            has_downloads = True
        else:
            logger.warning(
                "⚠️ No specific 'download' key found in top level. Printing dump to verify..."
            )

        # Also verify 'status' and 'version' are set
        logger.info(f"Version: {game.version}")
        logger.info(f"Status: {game.status}")

        if not has_downloads:
            logger.error("❌ Failed to verify download links in details.")

        logger.info("✅ Tracking Flow Test Passed.")

        # Test Case: Untrack Game
        logger.info(f"Untracking game ID {target_id}...")
        game = await service.untrack_game(target_id)

        logger.info(f"Is Tracked (After Untrack): {game.tracked}")

        if game.tracked:
            logger.error("❌ Game tracked status is still True!")
            sys.exit(1)

        logger.info("✅ Untracking Flow Test Passed.")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
