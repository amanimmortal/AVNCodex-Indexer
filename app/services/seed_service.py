import logging
import asyncio
import json
import os
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Game
from app.services.f95_client import F95ZoneClient
from app.database import AsyncSessionLocal
from sqlalchemy.future import select
from app.services.f95checker_client import F95CheckerClient
from app.services.game_service import GameService

from app.settings import settings

logger = logging.getLogger(__name__)

STATE_FILE = settings.SEED_STATE_FILE


class SeedService:
    def __init__(self):
        self.client = F95ZoneClient()
        self.checker_client = F95CheckerClient()
        self.page = 1
        self.enrichment_status = "idle"  # idle, seeding, enriching
        self.is_running = False
        self.items_processed = 0
        self.last_error = None
        self.was_running_on_shutdown = False
        self._load_state()

    def _load_state(self):
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r") as f:
                    state = json.load(f)
                    self.page = state.get("page", 1)
                    self.items_processed = state.get("items_processed", 0)
                    # If 'is_running' was True in the file, it means we shut down/crashed while running.
                    self.was_running_on_shutdown = state.get("is_running", False)
                    logger.info(
                        f"Loaded seed state: Page {self.page}, Items {self.items_processed}, Was Running: {self.was_running_on_shutdown}"
                    )
        except Exception as e:
            logger.error(f"Failed to load seed state: {e}")

    def _save_state(self):
        try:
            # Ensure dir exists (though main app likely created it for DB)
            os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
            with open(STATE_FILE, "w") as f:
                json.dump(
                    {
                        "page": self.page,
                        "items_processed": self.items_processed,
                        "is_running": self.is_running,
                    },
                    f,
                )
        except Exception as e:
            logger.error(f"Failed to save seed state: {e}")

    def get_status(self):
        return {
            "is_running": self.is_running,
            "current_page": self.page,
            "items_processed": self.items_processed,
            "last_error": str(self.last_error) if self.last_error else None,
            "status": self.enrichment_status,
        }

    async def seed_loop(self):
        """
        The main background loop.
        Crawls F95Zone alphabetically to index ALL games.
        """
        if self.is_running:
            logger.warning("Seed loop already running.")
            return

        self.is_running = True
        self._save_state()  # Persist running state
        self.last_error = None
        self.enrichment_status = "seeding"
        logger.info(f"Starting Alphabetical Seed Loop from Page {self.page}...")

        try:
            # Authenticate first
            logger.info("Authenticating with F95Zone...")
            # Run blocking login in thread
            await asyncio.to_thread(self.client.login)

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
                    logger.info(
                        "No data returned. Seeding complete or error. Switching to Enrichment."
                    )
                    break

                # 2. Upsert Games
                async with AsyncSessionLocal() as session:
                    count = 0
                    for data in games_data:
                        await self._upsert_game_basic(session, data)
                        count += 1
                    await session.commit()

                self.items_processed += count
                logger.info(f"Upserted {count} games from page {self.page}.")

                # 3. Pagination & Sleep
                self.page += 1
                self._save_state()  # Save progress

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

            # Start Enrichment Phase
            await self.enrichment_loop()

        except Exception as e:
            self.last_error = str(e)
            logger.error(f"Seeding crashed: {e}")
        finally:
            self.is_running = False
            self.enrichment_status = "idle"
            self._save_state()  # Persist stopped state
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

        # Cover URL from API
        game.cover_url = (
            data.get("cover_url")
            or data.get("featured_image")
            or data.get("image_url")
            or data.get("cover")
            or game.cover_url
        )

        # Date from F95Zone
        if data.get("ts"):
            try:
                from datetime import datetime

                game.f95_last_update = datetime.fromtimestamp(float(data["ts"]))
            except (ValueError, TypeError):
                pass
        elif data.get("date"):
            try:
                from datetime import datetime

                game.f95_last_update = datetime.fromtimestamp(float(data["date"]))
            except (ValueError, TypeError):
                pass

        # We strictly avoid overwriting 'status' or 'tags' here.

        session.add(game)

    async def enrichment_loop(self):
        """
        Slowly iterate through games that lack 'last_enriched' and fetch details from F95Checker.
        """
        self.enrichment_status = "enriching"
        logger.info("Starting Slow Enrichment Loop...")

        while True:
            if not self.is_running:
                break

            async with AsyncSessionLocal() as session:
                # 1. Fetch Candidates (Not enriched yet)
                stmt = select(Game).where(Game.last_enriched.is_(None)).limit(10)
                result = await session.execute(stmt)
                candidates = result.scalars().all()

                if not candidates:
                    logger.info("No more games to enrich. Enrichment loop finished.")
                    break

                ids = [g.f95_id for g in candidates]
                logger.info(f"Enriching batch of {len(ids)} games: {ids}")

                # 2. Fast Check (1 API Call)
                try:
                    timestamps_map = await asyncio.to_thread(
                        self.checker_client.check_updates, ids
                    )

                    # 3. Full Details (Up to 10 API Calls)
                    # Use GameService to handle logic reuse
                    game_service = GameService(session)

                    for game in candidates:
                        if not self.is_running:
                            break

                        tid = game.f95_id
                        ts = timestamps_map.get(tid)

                        if ts:
                            # Verify if it really needs update?
                            # We are here because last_enriched is None, so yes.

                            # Delay to be polite
                            await asyncio.sleep(2)

                            try:
                                details = await asyncio.to_thread(
                                    self.checker_client.get_game_details, tid, ts
                                )
                                if details:
                                    game_service.update_game_with_checker_details(
                                        game, details, ts
                                    )
                                    logger.info(f"Enriched {tid} successfully.")
                                else:
                                    logger.warning(f"Failed to get details for {tid}")
                            except Exception as e:
                                logger.error(f"Error enriching {tid}: {e}")
                        else:
                            # Not found in F95Checker?
                            # We might want to mark it as enriched to avoid infinite loop
                            # or handle it differently.
                            # For now, let's skip and maybe retry later or set a flag?
                            # If we don't set last_enriched, it will be picked up again next loop.
                            # DANGER: Infinite loop if F95Checker doesn't have the game.
                            # FIX: Set last_enriched to now even if not found?
                            # Or maybe just log it.
                            # Let's assume most games are there.
                            # If not found, we should probably mark it to skip.
                            logger.warning(
                                f"Game {tid} not found in F95Checker fast check."
                            )

                            # Mark as 'checked' effectively by setting last_enriched
                            # so we don't loop forever on it.
                            from datetime import datetime, timezone

                            game.last_enriched = datetime.now(timezone.utc)
                            session.add(game)

                    await session.commit()

                except Exception as e:
                    logger.error(f"Enrichment batch failed: {e}")

            # 4. Long Sleep between batches
            logger.info("Enrichment batch done. Sleeping 60 seconds...")
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
