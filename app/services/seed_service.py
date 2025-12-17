import logging
import asyncio
from typing import Optional
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Game
from app.services.f95_client import F95ZoneClient
from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


class SeedService:
    def __init__(self):
        self.client = F95ZoneClient()
        # TODO: Persist state in a file or DB. For now, in-memory or derived.
        self.page = 1
        self.is_running = False

    async def seed_loop(self):
        """
        The main background loop.
        Crawls F95Zone alphabetically to index ALL games.
        """
        if self.is_running:
            logger.warning("Seed loop already running.")
            return

        self.is_running = True
        logger.info("Starting Alphabetical Seed Loop...")

        try:
            while True:
                # 1. Fetch Page
                logger.info(f"Seeding Page {self.page} (sort=title)...")
                # Run sync client in thread to avoid blocking main loop
                games_data = await asyncio.to_thread(
                    self.client.get_latest_updates,
                    page=self.page,
                    rows=60,
                    sort="title",
                )

                if not games_data:
                    # End of list or error?
                    # Check if error or just empty
                    # For now, assume empty means done if page > 1
                    logger.info("No data returned. Seeding complete or error.")
                    break

                # 2. Upsert Games
                async with AsyncSessionLocal() as session:
                    count = 0
                    for data in games_data:
                        await self._upsert_game_basic(session, data)
                        count += 1
                    await session.commit()

                logger.info(f"Upserted {count} games from page {self.page}.")

                # 3. Pagination & Sleep
                self.page += 1

                # Check "Total Pages" if available in response?
                # Client returns list, not full dict with pagination metadata.
                # Use empty list check as break condition for now.

                # Sleep 5 minutes
                logger.info("Sleeping 5 minutes...")
                try:
                    await asyncio.sleep(300)
                except asyncio.CancelledError:
                    logger.info("Seeding cancelled during sleep.")
                    break

        except Exception as e:
            logger.error(f"Seeding crashed: {e}")
        finally:
            self.is_running = False
            logger.info("Seed loop stopped.")

    async def _upsert_game_basic(self, session: AsyncSession, data: dict):
        """
        Upsert Basic Info ONLY. Do not touch tags/status.
        """
        tid = data.get("thread_id")
        if not tid:
            return

        tid = int(tid)
        game = await session.get(Game, tid)
        if not game:
            game = Game(f95_id=tid, name=data.get("title") or "Unknown")

        # Update Basic Fields
        game.name = data.get("title") or game.name
        game.creator = data.get("creator") or game.creator
        game.version = data.get("version")

        # Date from F95Zone is usually relative "51 mins" or "Yesterday"
        # We assume 'ts' is better if available, but 'get_latest_updates' might not return 'ts' in 'list' mode?
        # Actually API response usually has 'date' string.
        # We strictly avoid overwriting 'status' or 'tags' here.

        session.add(game)
