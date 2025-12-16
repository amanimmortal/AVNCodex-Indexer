import logging
import json
from datetime import datetime
from typing import List, Optional
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Game
from app.services.f95_client import F95ZoneClient
from app.services.rss_client import RSSClient
from app.services.f95checker_client import F95CheckerClient

logger = logging.getLogger(__name__)


class GameService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.f95_client = F95ZoneClient()
        self.rss_client = RSSClient()
        self.checker_client = F95CheckerClient()

    async def track_game(self, thread_id: int) -> Game:
        """
        Enable tracking for a game and immediately sync details (downloads).
        """
        game = await self.get_game_by_id(thread_id)
        if not game:
            # If game doesn't exist locally, we must fetch it first.
            # We can try to fetch via force_update logic or just generic "get".
            # For now, let's assume we try to get it via force_update (which tries F95Checker/Direct).
            game = await self.force_update_game(thread_id)
            if not game:
                # Still not found? Create a stub?
                # User requirement: "searched for using the id to maintain preciseness"
                # If we really can't find it, we create it.
                game = Game(id=thread_id)
                self.session.add(game)

        game.tracked = True
        self.session.add(game)
        await self.session.commit()
        await self.session.refresh(game)

        # Trigger immediate sync for this game to get downloads
        # We can reuse the specific sync logic
        await self.sync_tracked_games(specific_ids=[thread_id])
        await self.session.refresh(game)
        return game

    async def untrack_game(self, thread_id: int) -> Game:
        """
        Disable tracking for a game.
        """
        game = await self.get_game_by_id(thread_id)
        if not game:
            raise ValueError(f"Game with ID {thread_id} not found locally.")

        game.tracked = False
        self.session.add(game)
        await self.session.commit()
        await self.session.refresh(game)
        return game

    async def sync_tracked_games(self, specific_ids: List[int] = None):
        """
        Check for updates for tracked games using F95Checker API.
        """
        if specific_ids:
            ids_to_check = specific_ids
        else:
            # Get all tracked games
            stmt = select(Game.id).where(Game.tracked.is_(True))
            result = await self.session.execute(stmt)
            ids_to_check = result.scalars().all()

        if not ids_to_check:
            return

        logger.info(
            f"Checking updates for {len(ids_to_check)} tracked games via F95Checker..."
        )

        # Bulk check for timestamps
        # F95Checker /fast endpoint
        timestamps_map = self.checker_client.check_updates(ids_to_check)

        count = 0
        for tid, ts in timestamps_map.items():
            # Check if we need to update
            # Logic: If 'ts' > game.f95_last_update (or some other marker) or if specific_ids (force)
            # User said: "On first add... call extra sync... check for updates... if update... call extra sync"
            # If specific_ids is passed (e.g. on Track), we ALWAYS fetch.

            should_fetch = False
            game = await self.get_game_by_id(tid)
            if not game:
                continue  # Should exist if we queried it, but safety first

            if specific_ids:
                should_fetch = True
            elif not game.f95_last_update:
                should_fetch = True
            # Note: F95Checker TS is seconds, verify game.f95_last_update is comparable
            # f95_last_update is datetime.
            elif datetime.fromtimestamp(ts) > game.f95_last_update:
                should_fetch = True

            if should_fetch:
                logger.info(f"Fetching full details for tracked game {tid}...")
                details = self.checker_client.get_game_details(tid, ts)
                if details:
                    self._update_game_with_checker_details(game, details, ts)
                    count += 1

        await self.session.commit()
        logger.info(f"Synced {count} tracked games.")

    def _update_game_with_checker_details(self, game: Game, details: dict, ts: int):
        """
        Merge F95Checker details into game object.
        """
        # Update core fields if they seem valid/newer
        # Checker usually has good versioning
        game.version = details.get("version") or game.version
        game.status = str(
            details.get("status")
        )  # Map if needed, but Checker sends ints/strings?
        # F95Checker status is often integer code? Need to verify.
        # But 'details' from checker might have mapped it?
        # Inspecting F95CheckerClient... it returns resp.json().
        # We assume it sends useful data.

        game.f95_last_update = datetime.fromtimestamp(ts)
        game.last_updated_at = datetime.utcnow()

        # Merge details_json
        current_details = {}
        if game.details_json:
            try:
                current_details = json.loads(game.details_json)
            except Exception:
                pass

        # Update with new keys (e.g. 'download_links')
        # We prefer Checker's data for downloads
        current_details.update(details)
        game.details_json = json.dumps(current_details)
        self.session.add(game)

    async def get_game_by_id(self, thread_id: int) -> Optional[Game]:
        result = await self.session.execute(select(Game).where(Game.id == thread_id))
        return result.scalar_one_or_none()

    async def search_local(self, query: str) -> List[Game]:
        stmt = select(Game).where(Game.name.ilike(f"%{query}%"))
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def search_and_index(self, query: str) -> List[Game]:
        """
        Hybrid search: Local -> Direct -> RSS -> F95Checker
        """
        # 1. Local Search
        local_results = await self.search_local(query)
        # Note: If local results exist but are stale, the scheduler handles them.
        # But if the user wants "fresh", they use force_refresh.
        # Here we return what we have to be fast.
        if local_results:
            logger.info(f"Found {len(local_results)} games locally for '{query}'")
            return local_results

        logger.info(f"No local results for '{query}'. Initiating remote search.")

        # 2. Remote Search (Direct F95)
        # Note: Direct Search returns List[Dict] with rich metadata
        remote_matches = self.f95_client.search_games(query)

        if not remote_matches:
            logger.info("Direct search yielded no results. Trying RSS.")
            # 3. RSS Search
            # RSS gives less data but might find things Direct misses?
            remote_matches = self.rss_client.get_games(search=query)
            # RSS matches need to be normalized to match Direct structure if possible,
            # or handled separately.

            if not remote_matches:
                logger.info("RSS search yielded no results.")
                return []

        # Process Results
        saved_games = []
        for data in remote_matches:
            # key mapping
            tid = data.get("thread_id") or data.get("id")
            if not tid:
                continue

            tid = int(tid)

            # Check DB again for individual ID to avoid duplicate insert error on race condition
            game = await self.get_game_by_id(tid)
            if not game:
                game = Game(id=tid)

            # Map Fields
            game.name = data.get("title") or data.get("name")
            game.author = data.get("creator") or data.get("author")
            game.version = data.get("version")

            # Status Logic
            # Direct API uses 'prefixes' list
            prefixes = data.get("prefixes", [])
            status = "Ongoing"  # Default
            if 18 in prefixes:
                status = "Completed"
            elif 20 in prefixes:
                status = "On Hold"
            elif 22 in prefixes:
                status = "Abandoned"

            # RSS might provide status in 'tags' or title [Prefix] if we parsed it?
            # RSSClient._parse_entry doesn't deeply parse status yet, usually "Unknown".
            if "prefixes" not in data and "status" not in data:
                # If coming from RSS, we might not have status.
                # We leave it as is (None/Unknown) or Default.
                pass
            elif "status" in data:
                status = data["status"]

            game.status = status

            # Timestamp Logic
            # Direct API has 'ts' (epoch)
            ts = data.get("ts")
            if ts:
                game.f95_last_update = datetime.fromtimestamp(int(ts))

            game.last_updated_at = datetime.utcnow()

            # Full Details
            # Store the *entire* raw data blob so we have tags, rating, covers etc.
            # This fulfills "all relevent data"
            game.details_json = json.dumps(data)

            self.session.add(game)
            saved_games.append(game)

        await self.session.commit()
        for g in saved_games:
            await self.session.refresh(g)

        return saved_games

    async def update_latest_games(self):
        """
        Scheduled job logic:
        1. Fetch latest updates from F95 Direct API and upsert.
        2. Sync tracked games via F95Checker logic.
        """
        # 1. Global Sync
        updates = self.f95_client.get_latest_updates(rows=90)  # Top 90
        logger.info(f"Fetched {len(updates)} updates from F95Zone.")

        count = 0
        for data in updates:
            tid = data.get("thread_id")
            if not tid:
                continue

            game = await self.get_game_by_id(int(tid))
            if not game:
                game = Game(id=int(tid))

            game.name = data.get("title")
            game.version = data.get("version")
            game.author = data.get("creator")
            game.last_updated_at = datetime.utcnow()

            # data has 'date' string usually

            self.session.add(game)
            count += 1

        await self.session.commit()
        logger.info(f"Upserted {count} games.")

        # 2. Tracked Sync
        await self.sync_tracked_games()

    async def force_update_game(self, thread_id: int):
        """
        Forces a comprehensive update for a single game ID.
        """
        # 1. Try Direct
        # Direct API 'list' command doesn't easily fetch by ID unless we search by exact title?
        # Actually we can do nothing but assume if we search by ID maybe?
        # Or we use the specific game logic if we had it.
        # But we can try F95Checker first if we just want metadata?
        # Or search by known name.

        game = await self.get_game_by_id(thread_id)
        if not game:
            logger.warning(
                f"Cannot force update unknown game ID {thread_id} without name reference for Direct API."
            )
            # We can try F95Checker ID check!
            # It's our fallback but essentially our best "ID-only" tool.

        # Try F95Checker for status/version
        # Get timestamp first
        timestamps = self.checker_client.check_updates([thread_id])
        if thread_id in timestamps:
            details = self.checker_client.get_game_details(
                thread_id, timestamps[thread_id]
            )
            if details:
                if not game:
                    game = Game(id=thread_id)
                game.name = details.get("name") or game.name
                game.version = details.get("version")
                game.status = str(details.get("status"))  # 0=Ongoing etc
                game.details_json = json.dumps(details)
                game.last_updated_at = datetime.utcnow()

                self.session.add(game)
                await self.session.commit()
                await self.session.refresh(game)
                return game

        return game
