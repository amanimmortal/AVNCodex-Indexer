import asyncio
import logging
import json
from datetime import datetime
import sys
import os

# Ensure we can import app modules
sys.path.append(os.getcwd())

from app.database import init_db, engine
from app.services.game_service import GameService
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from app.models import Game
from sqlmodel import SQLModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    # Setup connection
    db_file = "data/test_real_filters_v2.db"
    if os.path.exists(db_file):
        try:
            os.remove(db_file)
        except PermissionError:
            logger.warning("Could not delete existing DB, trying v3...")
            db_file = "data/test_real_filters_v3.db"
            if os.path.exists(db_file):
                os.remove(db_file)

    test_db_url = f"sqlite+aiosqlite:///{db_file}"
    test_engine = create_async_engine(test_db_url, echo=False, future=True)

    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async_session = sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        service = GameService(session)

        # 1. Fetch "Eternum" (known good game with tags)
        logger.info("=== 1. Fetching 'Eternum' from Remote ===")
        search_term = "Eternum"
        games = await service.search_and_index(query=search_term)

        target_game = None
        if not games:
            logger.warning(
                "Remote search returned no results (likely 429 or Login fail). Inserting fallback data to test FILTER logic."
            )
            # fallback: manually insert a game that mimics real data
            fallback_game = Game(
                id=999999,
                name="Eternum (Fallback)",
                status="Ongoing",
                version="0.6",
                f95_last_update=datetime.utcnow(),
                details_json=json.dumps(
                    {
                        "title": "Eternum (Fallback)",
                        "tags": ["adventure", "sci-fi"],
                        "status": "Ongoing",
                    }
                ),
            )
            session.add(fallback_game)
            await session.commit()
            games = [fallback_game]

        target_game = games[0]
        logger.info(f"Using Game: {target_game.name} (Status: {target_game.status})")

        # 2. Inspect Tags
        if target_game.details_json:
            data = json.loads(target_game.details_json)
            tags = data.get("tags", [])
            logger.info(f"Tags Found: {tags}")

            if tags:
                test_tag = tags[0]
                if isinstance(test_tag, dict):
                    test_tag_str = str(test_tag)
                else:
                    test_tag_str = str(test_tag)

                logger.info(f"Testing Filter with Tag: '{test_tag_str}'")

                # 3. Test Tag Filter (Success)
                logger.info("=== 3. Testing Tag Filter (Should Match) ===")
                filtered_games = await service.search_and_index(
                    query=None, tags=[test_tag_str]
                )

                if filtered_games:
                    logger.info(
                        f"SUCCESS: Found {len(filtered_games)} games with tag '{test_tag_str}'"
                    )
                else:
                    logger.error(
                        f"FAILURE: Tag filter '{test_tag_str}' returned nothing!"
                    )

                # 4. Test Tag Filter (Fail)
                logger.info("=== 4. Testing Tag Filter (Should Fail) ===")
                fake_tag = "NonExistentTagXYZ"
                filtered_games_fail = await service.search_and_index(
                    query=None, tags=[fake_tag]
                )
                if not filtered_games_fail:
                    logger.info("SUCCESS: correctly returned no results for fake tag.")
                else:
                    logger.error("FAILURE: Found games for fake tag!")

        # 5. Test Status Filter
        logger.info(f"=== 5. Testing Status Filter: '{target_game.status}' ===")
        filtered_status = await service.search_and_index(
            query=None, status=target_game.status
        )
        if filtered_status:
            logger.info(
                f"SUCCESS: Found {len(filtered_status)} games with status '{target_game.status}'"
            )
        else:
            logger.error("FAILURE: Status filter returned nothing!")

        # 6. Test Date Filter
        past_date = datetime(2020, 1, 1)
        logger.info(f"=== 6. Testing Date Filter: Updated After {past_date} ===")
        filtered_date = await service.search_and_index(
            query=None, updated_after=past_date
        )
        if filtered_date:
            logger.info(f"SUCCESS: Found {len(filtered_date)} games updated after 2020")
        else:
            logger.error("FAILURE: Date filter returned nothing")


if __name__ == "__main__":
    try:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
