import logging
import asyncio
import json
import os
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Game
from app.services.f95_client import F95ZoneClient
from app.database import AsyncSessionLocal

from app.settings import settings

logger = logging.getLogger(__name__)

STATE_FILE = settings.SEED_STATE_FILE


class SeedService:
    def __init__(self):
        self.client = F95ZoneClient()
        self.page = 1
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
                    logger.info("No data returned. Seeding complete or error.")
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

        except Exception as e:
            self.last_error = str(e)
            logger.error(f"Seeding crashed: {e}")
        finally:
            self.is_running = False
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
