import logging
import asyncio
import json
import os
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Game
from app.services.f95_client import F95ZoneClient
from app.database import AsyncSessionLocal
from sqlalchemy.future import select
from sqlalchemy import func
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
        self.max_processed_id = 0
        self.last_run_completion_time = 0.0
        self.pending_enrichment_count = 0
        self.estimated_seconds_remaining = 0
        self._load_state()

    def _load_state(self):
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r") as f:
                    state = json.load(f)
                    self.page = state.get("page", 1)
                    self.items_processed = state.get("items_processed", 0)
                    self.enrichment_status = state.get("enrichment_status", "idle")
                    # If 'is_running' was True in the file, it means we shut down/crashed while running.
                    self.was_running_on_shutdown = state.get("is_running", False)
                    self.max_processed_id = state.get("max_processed_id", 0)
                    self.last_run_completion_time = state.get(
                        "last_run_completion_time", 0.0
                    )
                    logger.info(
                        f"Loaded seed state: Page {self.page}, Items {self.items_processed}, Status {self.enrichment_status}, "
                        f"MaxID {self.max_processed_id}, LastRun {self.last_run_completion_time}"
                    )
        except Exception as e:
            logger.error(f"Failed to load seed state: {e}")

    async def _save_state(self):
        try:
            # Ensure dir exists
            from pathlib import Path

            path = Path(STATE_FILE).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)

            temp_path = path.with_suffix(".tmp")

            # Atomic write: Write to temp -> Rename
            # Use run_in_executor for file I/O to avoid blocking loop
            await asyncio.to_thread(self._write_file_atomic, path, temp_path)

        except Exception as e:
            logger.error(f"Failed to save seed state: {e}")

    def _write_file_atomic(self, path, temp_path):
        with open(temp_path, "w") as f:
            json.dump(
                {
                    "page": self.page,
                    "items_processed": self.items_processed,
                    "is_running": self.is_running,
                    "enrichment_status": self.enrichment_status,
                    "max_processed_id": self.max_processed_id,
                    "last_run_completion_time": self.last_run_completion_time,
                },
                f,
            )
        os.replace(temp_path, path)

    def get_status(self):
        return {
            "is_running": self.is_running,
            "current_page": self.page,
            "items_processed": self.items_processed,
            "last_error": str(self.last_error) if self.last_error else None,
            "status": self.enrichment_status,
            "max_processed_id": self.max_processed_id,
            "last_run_completion_time": self.last_run_completion_time,
            "pending_enrichment_count": self.pending_enrichment_count,
            "estimated_seconds_remaining": self.estimated_seconds_remaining,
        }

    async def seed_loop(self, reset: bool = False):
        """
        The main background loop.
        Modes:
        1. Full Reset (reset=True): Alphabetical scan (sort='title'), wipes state, indexes EVERYTHING.
        2. Incremental (reset=False): Date scan (sort='date'), only updates new games (id > max),
           stops when reaching previous run time.
        """
        interrupted = False
        import time

        if reset:
            self.page = 1
            self.items_processed = 0
            self.enrichment_status = "idle"
            self.max_processed_id = 0
            self.last_run_completion_time = 0.0
            await self._save_state()
            logger.info("Seeding reset to Page 1 (Full Reseed).")

        if self.is_running:
            logger.warning(
                "Seed loop already running. State has been reset if requested."
            )
            return

        self.is_running = True
        await self._save_state()  # Persist running state
        self.last_error = None

        if self.enrichment_status == "enriching":
            logger.info("Resuming Enrichment Loop directly...")
            await self.enrichment_loop()
            self.is_running = False
            await self._save_state()
            return

        self.enrichment_status = "seeding"

        # DETERMINE MODE
        # If we have a last_run_time and NOT resetting, we do Incremental
        # Otherwise (reset=True or fresh install), we do Full (Title Sort)
        is_incremental = (not reset) and (self.last_run_completion_time > 0)
        sort_mode = "date" if is_incremental else "title"

        logger.info(
            f"Starting Seed Loop. Mode={'Incremental' if is_incremental else 'Full'} (Sort={sort_mode}). Page {self.page}..."
        )
        if is_incremental:
            logger.info(
                f"Incremental Constraints: Skip ID <= {self.max_processed_id}, Stop if Date < {self.last_run_completion_time}"
            )

        previous_page_ids = set()

        # Track start time to update last_run_completion_time ONLY on success
        run_start_time = time.time()

        try:
            # Authenticate first
            logger.info("Authenticating with F95Zone...")
            await asyncio.to_thread(self.client.login)

            while True:
                # 1. Fetch Page
                logger.info(f"Seeding Page {self.page} (sort={sort_mode})...")
                games_data = await asyncio.to_thread(
                    self.client.get_latest_updates,
                    page=self.page,
                    rows=60,
                    sort=sort_mode,
                )

                if games_data is None:
                    logger.error(
                        f"Failed to fetch page {self.page}. Retrying in 60s..."
                    )
                    try:
                        await asyncio.sleep(60)
                    except asyncio.CancelledError:
                        break
                    continue

                if not games_data:
                    logger.info("No data returned (Empty List). Seeding complete.")
                    break

                # CHECK FOR INFINITE LOOP
                current_ids = {
                    g.get("thread_id") for g in games_data if g.get("thread_id")
                }
                if previous_page_ids and current_ids == previous_page_ids:
                    logger.warning("Page content IDENTICAL to previous. Breaking loop.")
                    break
                previous_page_ids = current_ids

                # 2. Upsert Games
                async with AsyncSessionLocal() as session:
                    count = 0
                    skipped_old = 0
                    stop_signal = False

                    for data in games_data:
                        tid = data.get("thread_id")
                        if not tid:
                            continue
                        tid = int(tid)

                        # PARSE DATE for stop condition
                        # Try 'ts' (float) then 'date' (usually string relative, but sometimes absolute?)
                        # We prefer 'ts'
                        game_ts = 0.0
                        if data.get("ts"):
                            try:
                                game_ts = float(data["ts"])
                            except (ValueError, TypeError):
                                pass

                        if is_incremental:
                            # STOP LOGIC: If game update time is older than our last run, we are done.
                            # We buffer slightly (e.g. strict <)
                            if game_ts > 0 and game_ts < self.last_run_completion_time:
                                logger.info(
                                    f"Stop Condition Met: Game {tid} ts {game_ts} < Last Run {self.last_run_completion_time}"
                                )
                                stop_signal = True
                                break

                            # SKIP LOGIC: If game ID is old, we don't need to check it
                            # (Assuming we only want NEW games as per user request)
                            if tid <= self.max_processed_id:
                                skipped_old += 1
                                continue

                        await self._upsert_game_basic(session, data)
                        count += 1

                        # Update max_processed_id on the fly
                        if tid > self.max_processed_id:
                            self.max_processed_id = tid  # Update in memory immediately

                    await session.commit()

                self.items_processed += count
                logger.info(
                    f"Page {self.page}: Upserted {count}, Skipped {skipped_old} (Old). MaxID: {self.max_processed_id}"
                )

                if stop_signal:
                    logger.info("Incremental Seeding Finished (Time limit reached).")
                    break

                # 3. Pagination & Sleep
                self.page += 1
                await self._save_state()
                await asyncio.sleep(settings.SEED_PAGE_DELAY)

            # END OF LOOP

            # If we finished successfully (break), update last_run_time
            # ONLY if we actually did something or verified checks.
            # If we were in incremental mode, we just caught up.
            # If full mode, we indexed everything.
            self.last_run_completion_time = run_start_time

            logger.info("Seeding Phase Complete. Transitioning to Enrichment.")

            # Reset page for enrichment
            self.page = 1
            await self._save_state()
            await self.enrichment_loop()

        except asyncio.CancelledError:
            interrupted = True
            logger.info("Seed loop cancelled (Shutdown detected).")
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"Seeding crashed: {e}")
        finally:
            if interrupted:
                self.is_running = True  # Resume next time
            else:
                if self.is_running:
                    self.is_running = False
                    self.enrichment_status = "idle"

            await self._save_state()
            logger.info(f"Seed loop stopped. (Interrupted={interrupted})")

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
        # Reset page to 1 for "Batch 1" visualization, but keep items_processed from seeding phase
        # or should we count items processed IN TOTAL? Yes, let's keep adding to it.
        self.page = 1
        await self._save_state()
        await self._save_state()
        logger.info("Starting Slow Enrichment Loop...")

        # Update initial pending count
        async with AsyncSessionLocal() as session:
            await self._update_pending_count(session)

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

                    # Auto-reset state for next run
                    self.page = 1
                    self.items_processed = 0
                    self.enrichment_status = "idle"
                    self.is_running = False
                    await self._save_state()
                    logger.info(
                        "Seed state auto-reset to Page 1 (Idle).Ready for next run."
                    )
                    break

                ids = [g.f95_id for g in candidates]
                logger.info(f"Enriching batch {self.page} of {len(ids)} games: {ids}")

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

                    # Update Progress & Metrics
                    self.items_processed += len(candidates)
                    self.page += 1
                    await self._update_pending_count(session)
                    await self._save_state()

                except Exception as e:
                    logger.error(f"Enrichment batch failed: {e}")

            # 4. Long Sleep between batches
            logger.info("Enrichment batch done. Sleeping 60 seconds...")
            await asyncio.sleep(60)

    async def _update_pending_count(self, session: AsyncSession):
        """
        Update the count of games pending enrichment and estimated time.
        """
        try:
            # Count games where last_enriched is None
            stmt = select(func.count(Game.id)).where(Game.last_enriched.is_(None))
            result = await session.execute(stmt)
            count = result.scalar() or 0

            self.pending_enrichment_count = count

            # Estimate: (2s per game) + (60s overhead per batch of 10)
            # Batch size = 10
            # Time per batch = 10*2 + 60 = 80s
            # Avg time per game = 8s
            self.estimated_seconds_remaining = count * 8

        except Exception as e:
            logger.error(f"Failed to update pending enrichment count: {e}")
