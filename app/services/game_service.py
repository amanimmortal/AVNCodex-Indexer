import logging
import json
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from sqlalchemy.future import select
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import BackgroundTasks
from app.models import Game
from app.services.f95_client import F95ZoneClient
from app.services.rss_client import RSSClient
from app.services.f95checker_client import F95CheckerClient
from app.database import AsyncSessionLocal
from app.settings import settings

logger = logging.getLogger(__name__)


async def standalone_force_update(thread_id: int):
    """
    Background task to update a game with a fresh session.
    Helper function to run in background tasks where the request session is closed.
    """
    async with AsyncSessionLocal() as session:
        service = GameService(session)
        await service.force_update_game(thread_id)


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
            game = await self.force_update_game(thread_id)
            if not game:
                game = Game(f95_id=thread_id, name="Unknown")
                self.session.add(game)

        game.tracked = True
        self.session.add(game)
        await self.session.commit()
        await self.session.refresh(game)

        # Trigger immediate sync for this game
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
            stmt = select(Game.f95_id).where(Game.tracked.is_(True))
            result = await self.session.execute(stmt)
            ids_to_check = result.scalars().all()

        if not ids_to_check:
            return

        logger.info(
            f"Checking updates for {len(ids_to_check)} tracked games via F95Checker..."
        )

        timestamps_map = await asyncio.to_thread(
            self.checker_client.check_updates, ids_to_check
        )

        count = 0
        for tid, ts in timestamps_map.items():
            should_fetch = False
            game = await self.get_game_by_id(tid)
            if not game:
                continue

            if specific_ids:
                should_fetch = True
            elif not game.f95_last_update:
                should_fetch = True
            elif datetime.fromtimestamp(ts) > game.f95_last_update:
                should_fetch = True

            if should_fetch:
                logger.info(f"Fetching full details for tracked game {tid}...")
                details = await asyncio.to_thread(
                    self.checker_client.get_game_details, tid, ts
                )
                if details:
                    self.update_game_with_checker_details(game, details, ts)
                    count += 1

        await self.session.commit()
        logger.info(f"Synced {count} tracked games.")

    def update_game_with_checker_details(self, game: Game, details: dict, ts: int):
        """
        Merge F95Checker details into game object.
        """
        game.version = details.get("version") or game.version
        game.status = str(details.get("status"))

        # Populate IDs
        if details.get("type"):
            try:
                game.type_id = int(details.get("type"))
            except (ValueError, TypeError):
                pass

        if details.get("status"):
            try:
                game.status_id = int(details.get("status"))
            except (ValueError, TypeError):
                pass

        if details.get("rating"):
            try:
                game.rating = float(details.get("rating"))
            except (ValueError, TypeError):
                pass

        if details.get("likes"):
            try:
                game.likes = int(details.get("likes"))
            except (ValueError, TypeError):
                pass

        # Date Logic: Prefer 'last_updated' from full details (actual index time)
        # over 'ts' (fast check time), which might just be a staleness check.
        if details.get("last_updated"):
            try:
                # F95Checker API returns string or int timestamp
                ts_val = float(details["last_updated"])
                game.f95_last_update = datetime.fromtimestamp(ts_val)
                logger.info(
                    f"Enriched game {game.f95_id} with FULL update time: {game.f95_last_update}"
                )
            except (ValueError, TypeError):
                # Fallback if parse fails
                game.f95_last_update = datetime.fromtimestamp(ts)
                logger.warning(
                    f"Failed to parse 'last_updated', using FAST check time: {game.f95_last_update}"
                )
        else:
            game.f95_last_update = datetime.fromtimestamp(ts)
            logger.info(
                f"Field 'last_updated' missing, using FAST check time: {game.f95_last_update}"
            )

        game.last_updated_at = datetime.now(timezone.utc)
        game.last_enriched = datetime.now(timezone.utc)

        # Tags update
        if details.get("tags"):
            game.tags = json.dumps(details.get("tags"))

        # Cover URL
        # F95Checker usually puts it in 'featured_image' or 'cover_url' or similar?
        # Based on legacy investigation, it might be just 'image_url' or passed in details.
        # We will check common keys.
        game.cover_url = (
            details.get("featured_image")
            or details.get("cover_url")
            or details.get("image_url")
            or details.get("cover")
            or game.cover_url
        )

        current_details = {}
        if game.details_json:
            try:
                current_details = json.loads(game.details_json)
            except Exception:
                pass

        current_details.update(details)
        game.details_json = json.dumps(current_details)
        self.session.add(game)

    async def get_game_by_id(self, thread_id: int) -> Optional[Game]:
        result = await self.session.execute(
            select(Game).where(Game.f95_id == thread_id)
        )
        return result.scalar_one_or_none()

    async def search_local(self, query: str) -> List[Game]:
        stmt = select(Game).where(Game.name.ilike(f"%{query}%"))
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def search_and_index(
        self,
        query: str = None,
        status: str = None,
        tags: List[str] = None,
        exclude_tags: List[str] = None,
        engine: int = None,
        updated_after: datetime = None,
        background_tasks: BackgroundTasks = None,
        page: int = 1,
        limit: int = 30,
        sort_by: str = "updated_at",
        sort_dir: str = "desc",
    ) -> List[Game]:
        """
        Refactored Search Logic (Local First with Remote Fallback).
        Supports Pagination, Freshness Caching, and Sorting.
        """
        # 1. Local Search (Priority)
        stmt = select(Game)
        if query:
            stmt = stmt.where(Game.name.ilike(f"%{query}%"))

        if status:
            # Try to filter by status_id if status is an integer string
            if status.isdigit():
                stmt = stmt.where(Game.status_id == int(status))
            else:
                stmt = stmt.where(Game.status == status)

        if engine:
            stmt = stmt.where(Game.type_id == engine)

        if tags:
            for tag in tags:
                stmt = stmt.where(Game.tags.contains(tag))

        if exclude_tags:
            for tag in exclude_tags:
                # Ensure we handle NULL tags (keep them)
                # Use explicit NOT LIKE to be safe
                stmt = stmt.where(
                    or_(Game.tags.is_(None), Game.tags.notlike(f"%{tag}%"))
                )

        if updated_after:
            stmt = stmt.where(Game.f95_last_update >= updated_after)

        # Sorting Logic
        if sort_by == "name":
            sort_col = Game.name
        elif sort_by == "rating":
            sort_col = Game.rating
        elif sort_by == "likes":
            sort_col = Game.likes
        else:
            # Default to updated_at
            sort_col = Game.f95_last_update

        if sort_dir == "asc":
            stmt = stmt.order_by(sort_col.asc().nulls_last())
        else:
            stmt = stmt.order_by(sort_col.desc().nulls_last())

        # Enforce Pagination
        offset = (page - 1) * limit
        stmt = stmt.offset(offset).limit(limit)

        result = await self.session.execute(stmt)
        local_results = result.scalars().all()

        if local_results:
            logger.info(f"Local hit: {len(local_results)} matches (Page {page}).")

            # --- Synchronous Freshness Check (Optimized) ---
            games_map = {g.f95_id: g for g in local_results}

            # Optimization: Only check items that haven't been enriched recently
            # "Recently" defined by settings.SEARCH_FRESHNESS_DAYS (default 7 days)
            now_utc = datetime.now(timezone.utc)
            cutoff_date = now_utc - timedelta(days=settings.SEARCH_FRESHNESS_DAYS)

            # Filter candidates
            ids_to_check = []
            for g in local_results:
                if not g.last_enriched:
                    ids_to_check.append(g.f95_id)
                elif g.last_enriched < cutoff_date:
                    ids_to_check.append(g.f95_id)

            if not ids_to_check:
                logger.info(
                    "All results are fresh per cached policy. Skipping API check."
                )
                return local_results

            logger.info(
                f"Freshness Check: Checking {len(ids_to_check)}/{len(local_results)} items (others cached < {settings.SEARCH_FRESHNESS_DAYS} days)"
            )

            # 1. Fast Check

            timestamps_map = await asyncio.to_thread(
                self.checker_client.check_updates, ids_to_check
            )

            # 2. Identify Stale
            to_fetch_details = []

            for gid, ts in timestamps_map.items():
                game = games_map.get(gid)
                if not game:
                    continue

                should_fetch = False

                # Condition A: Never enriched
                if not game.last_enriched:
                    should_fetch = True

                # Condition B: Timestamp mismatch (remote is newer)
                elif (
                    game.f95_last_update
                    and datetime.fromtimestamp(ts) > game.f95_last_update
                ):
                    should_fetch = True

                # Condition C: Very old enrichment (safety net, optional, e.g. > 30 days)
                # elif (now - game.last_enriched).days > 30:
                #    should_fetch = True

                if should_fetch:
                    to_fetch_details.append((gid, ts))

            # 3. Synchronous Fetch & Update
            if to_fetch_details:
                logger.info(
                    f"Syncing {len(to_fetch_details)} stale games synchronously..."
                )
                for gid, ts in to_fetch_details:
                    details = await asyncio.to_thread(
                        self.checker_client.get_game_details, gid, ts
                    )
                    if details:
                        # We reuse the helper, ensuring the object in session is updated
                        game = games_map[gid]
                        self.update_game_with_checker_details(game, details, ts)

                # Commit updates before returning
                await self.session.commit()
                # Refresh all to ensure return values are current
                for g in local_results:
                    await self.session.refresh(g)

            return local_results

        # 2. Remote Fallback (Only if we have a Name Query and NO results)
        if query and not local_results:
            logger.info(
                f"Local miss for '{query}'. Triggering Remote Search (F95Zone)."
            )

            remote_matches = await asyncio.to_thread(
                self.f95_client.search_games, query
            )

            # Limit Remote Results based on requested limit
            remote_matches = remote_matches[:limit]

            saved_games = []
            for data in remote_matches:
                tid = data.get("thread_id") or data.get("id")
                if not tid:
                    continue
                tid = int(tid)

                game = await self.get_game_by_id(tid)
                if not game:
                    game = Game(f95_id=tid, name=data.get("title") or "Unknown")

                game.name = data.get("title") or game.name
                game.creator = data.get("creator")
                game.version = data.get("version")

                game.cover_url = (
                    data.get("cover_url")
                    or data.get("featured_image")
                    or data.get("image_url")
                    or data.get("cover")
                    or game.cover_url
                )

                # Parse Date
                if data.get("date"):
                    try:
                        game.f95_last_update = datetime.fromtimestamp(
                            float(data["date"])
                        )
                    except (ValueError, TypeError):
                        pass

                self.session.add(game)
                saved_games.append(game)

            await self.session.commit()

            # --- Synchronous Enrichment for Remote Results ---
            # Make a quick pass to enrich these new findings if possible
            if saved_games:
                ids = [g.f95_id for g in saved_games]
                ts_map = await asyncio.to_thread(self.checker_client.check_updates, ids)

                updates_count = 0
                for game in saved_games:
                    ts = ts_map.get(game.f95_id)
                    if ts:
                        # Fetch details
                        details = await asyncio.to_thread(
                            self.checker_client.get_game_details, game.f95_id, ts
                        )
                        if details:
                            self.update_game_with_checker_details(game, details, ts)
                            updates_count += 1

                if updates_count > 0:
                    await self.session.commit()
                    for g in saved_games:
                        await self.session.refresh(g)

            return saved_games

        return []

    async def update_latest_games(self):
        """
        Scheduled job: Recent Updates.
        """
        self.f95_client.login()

        page = 1
        has_more = True

        while has_more:
            logger.info(f"Fetching Recent Updates Page {page}...")
            updates = await asyncio.to_thread(
                self.f95_client.get_latest_updates, page=page, sort="date"
            )

            if not updates:
                break

            count = 0
            for data in updates:
                tid = data.get("thread_id")
                if not tid:
                    continue
                tid = int(tid)

                game = await self.get_game_by_id(tid)
                if not game:
                    game = Game(f95_id=tid, name=data.get("title") or "Unknown")

                game.name = data.get("title") or game.name
                game.version = data.get("version")
                game.creator = data.get("creator")

                game.cover_url = (
                    data.get("cover_url")
                    or data.get("featured_image")
                    or data.get("image_url")
                    or data.get("cover")
                    or game.cover_url
                )

                # Parse Date from F95Zone result
                if data.get("ts"):
                    try:
                        game.f95_last_update = datetime.fromtimestamp(float(data["ts"]))
                    except (ValueError, TypeError):
                        pass
                elif data.get("date"):
                    try:
                        game.f95_last_update = datetime.fromtimestamp(
                            float(data["date"])
                        )
                    except (ValueError, TypeError):
                        pass

                self.session.add(game)
                count += 1

            await self.session.commit()
            logger.info(f"Upserted {count} games on page {page}.")

            if page >= 5:
                has_more = False
            else:
                page += 1

        # Trigger tracked sync after
        await self.sync_tracked_games()

    async def force_update_game(self, thread_id: int):
        """
        Force update using F95Checker logic.
        """
        game = await self.get_game_by_id(thread_id)
        if not game:
            pass  # Or create empty stub if strict

        timestamps = await asyncio.to_thread(
            self.checker_client.check_updates, [thread_id]
        )
        if thread_id in timestamps:
            details = await asyncio.to_thread(
                self.checker_client.get_game_details, thread_id, timestamps[thread_id]
            )
            if details:
                if not game:
                    game = Game(f95_id=thread_id, name=details.get("name") or "Unknown")

                game.name = details.get("name") or game.name
                game.version = details.get("version")
                game.cover_url = (
                    details.get("featured_image")
                    or details.get("cover_url")
                    or details.get("image_url")
                    or details.get("cover")
                    or game.cover_url
                )
                game.status = str(details.get("status"))
                if details.get("type"):
                    try:
                        game.type_id = int(details.get("type"))
                    except (ValueError, TypeError):
                        pass

                if details.get("status"):
                    try:
                        game.status_id = int(details.get("status"))
                    except (ValueError, TypeError):
                        pass

                game.tags = json.dumps(details.get("tags") or [])
                game.details_json = json.dumps(details)
                game.last_enriched = datetime.now(timezone.utc)
                game.f95_last_update = datetime.fromtimestamp(timestamps[thread_id])

                self.session.add(game)
                await self.session.commit()
                await self.session.refresh(game)

        return game
