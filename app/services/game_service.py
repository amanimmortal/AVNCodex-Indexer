import logging
import json
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from sqlalchemy.future import select
from sqlalchemy import or_, and_, cast, Float
from sqlalchemy.sql.functions import coalesce
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


async def standalone_process_search_updates(game_ids: List[int]):
    """
    Background task to process search result updates.
    Checks for updates and fetches details for stale items.
    """
    if not game_ids:
        return

    logger.info(f"Background Update: Starting check for {len(game_ids)} items.")

    async with AsyncSessionLocal() as session:
        service = GameService(session)
        checker_client = service.checker_client

        # 1. Fast Check
        timestamps_map = await checker_client.check_updates(game_ids)

        # 2. Identify Stale (Need to fetch current state from DB first)
        # We need to re-fetch the games because we are in a new session
        # and we need to check their current timestamp against the fast check result.

        stmt = select(Game).where(Game.f95_id.in_(list(timestamps_map.keys())))
        result = await session.execute(stmt)
        games = result.scalars().all()
        games_map = {g.f95_id: g for g in games}

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

            if should_fetch:
                to_fetch_details.append((gid, ts))

        # 3. Fetch & Update
        if to_fetch_details:
            logger.info(
                f"Background Update: Syncing {len(to_fetch_details)} stale games..."
            )
            count = 0
            for gid, ts in to_fetch_details:
                details = await checker_client.get_game_details(gid, ts)
                if details:
                    game = games_map.get(gid)
                    if game:
                        service.update_game_with_checker_details(game, details, ts)
                        count += 1

            await session.commit()
            logger.info(f"Background Update: Successfully updated {count} games.")
        else:
            logger.info(
                "Background Update: No items needed actual updates after check."
            )


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

        timestamps_map = await self.checker_client.check_updates(ids_to_check)

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
                details = await self.checker_client.get_game_details(tid, ts)
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

        # Parse Rating (Key is 'score' in F95Checker JSON)
        rating_val = details.get("rating") or details.get("score")
        if rating_val:
            try:
                game.rating = float(rating_val)
            except (ValueError, TypeError):
                pass

        # Parse Likes (Key might be 'votes' in F95Checker JSON)
        likes_val = details.get("likes") or details.get("votes")
        if likes_val:
            try:
                game.likes = int(likes_val)
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
        status: List[str] = None,
        exclude_status: List[str] = None,
        tags: List[str] = None,
        exclude_tags: List[str] = None,
        engine: List[int] = None,
        exclude_engine: List[int] = None,
        updated_after: datetime = None,
        background_tasks: BackgroundTasks = None,
        page: int = 1,
        limit: int = 30,
        sort_by: str = "updated_at",
        sort_dir: str = "desc",
        creator: str = None,
        tag_mode: str = "AND",
        tag_groups: str = None,
    ) -> List[Game]:
        """
        Refactored Search Logic (Local First with Remote Fallback).
        Supports Pagination, Freshness Caching, and Sorting.
        """
        # 1. Local Search (Priority)
        stmt = select(Game)
        if query:
            stmt = stmt.where(Game.name.ilike(f"%{query}%"))

        if creator:
            stmt = stmt.where(Game.creator.ilike(f"%{creator}%"))

        # --- Status Filtering ---
        if status:
            # Separate integers (IDs) from strings (Names) if mixed input
            # Though strictly type hinted as List[str], FastAPI might pass mixed if user does ?status=1
            status_ids = []
            status_names = []
            for s in status:
                if s.isdigit():
                    status_ids.append(int(s))
                else:
                    status_names.append(s)

            conditions = []
            if status_ids:
                conditions.append(Game.status_id.in_(status_ids))
            if status_names:
                conditions.append(Game.status.in_(status_names))

            if conditions:
                stmt = stmt.where(or_(*conditions))

        if exclude_status:
            ex_ids = []
            ex_names = []
            for s in exclude_status:
                if s.isdigit():
                    ex_ids.append(int(s))
                else:
                    ex_names.append(s)

            if ex_ids:
                stmt = stmt.where(Game.status_id.notin_(ex_ids))
            if ex_names:
                stmt = stmt.where(Game.status.notin_(ex_names))

        # --- Engine Filtering ---
        if engine:
            stmt = stmt.where(Game.type_id.in_(engine))

        if exclude_engine:
            stmt = stmt.where(Game.type_id.notin_(exclude_engine))

        if tags:
            tag_conditions = []
            for tag in tags:
                # Precise tag matching for JSON array string "[...]"
                # We expect tags to be double-quoted in JSON: ["Tag"]
                tag_q = f'"{tag}"'
                cond = or_(
                    Game.tags == f"[{tag_q}]",
                    Game.tags.like(f"[{tag_q}, %"),
                    Game.tags.like(f"%, {tag_q}]"),
                    Game.tags.like(f"%, {tag_q}, %"),
                )
                tag_conditions.append(cond)

            if tag_conditions:
                if tag_mode == "OR":
                    stmt = stmt.where(or_(*tag_conditions))
                else:
                    # Default AND: Must match ALL tags
                    for cond in tag_conditions:
                        stmt = stmt.where(cond)

        if tag_groups:
            try:
                groups = json.loads(tag_groups)
                # Groups Logic: (GroupA) OR (GroupB) ...
                # Inside Group: Tag1 AND Tag2 ...
                if isinstance(groups, list) and groups:
                    group_conditions = []
                    for group_tags in groups:
                        if not isinstance(group_tags, list) or not group_tags:
                            continue

                        # Build AND conditions for this group
                        current_group_and = []
                        for tag in group_tags:
                            tag_q = f'"{tag}"'
                            cond = or_(
                                Game.tags == f"[{tag_q}]",
                                Game.tags.like(f"[{tag_q}, %"),
                                Game.tags.like(f"%, {tag_q}]"),
                                Game.tags.like(f"%, {tag_q}, %"),
                            )
                            current_group_and.append(cond)

                        if current_group_and:
                            group_conditions.append(and_(*current_group_and))

                    if group_conditions:
                        stmt = stmt.where(or_(*group_conditions))
            except json.JSONDecodeError:
                logger.warning("Failed to parse tag_groups parameters as JSON.")

        if exclude_tags:
            for tag in exclude_tags:
                # Exclude if it matches any of the precise patterns
                # Handle NULLs safely (keep them if excluding a tag)
                stmt = stmt.where(
                    or_(
                        Game.tags.is_(None),
                        ~or_(
                            Game.tags == f"[{tag}]",
                            Game.tags.like(f"[{tag}, %"),
                            Game.tags.like(f"%, {tag}]"),
                            Game.tags.like(f"%, {tag}, %"),
                        ),
                    )
                )

        if updated_after:
            stmt = stmt.where(Game.f95_last_update >= updated_after)

        # Sorting Logic
        if sort_by == "name":
            sort_col = Game.name
        elif sort_by == "rating":
            # Weighted Rating (Bayesian Average)
            # WR = (v / (v+m)) * R + (m / (v+m)) * C
            # v = likes (coalesce to 0)
            # R = rating (coalesce to 0)
            # m = settings.WEIGHTED_RATING_MIN_VOTES
            # C = settings.WEIGHTED_RATING_GLOBAL_MEAN

            m = settings.WEIGHTED_RATING_MIN_VOTES
            C = settings.WEIGHTED_RATING_GLOBAL_MEAN

            # Cast inputs to Float to avoid integer division issues
            v = cast(coalesce(Game.likes, 0), Float)
            R = cast(coalesce(Game.rating, 0), Float)

            sort_col = (v / (v + m)) * R + (m / (v + m)) * C

        elif sort_by == "updated_at":
            sort_col = Game.f95_last_update
        else:
            # Default fallback
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

            # Optimization: Only check items that haven't been enriched recently
            # "Recently" defined by settings.SEARCH_FRESHNESS_DAYS (default 7 days)
            now_utc = datetime.now(timezone.utc)
            cutoff_date = now_utc - timedelta(days=settings.SEARCH_FRESHNESS_DAYS)

            # Filter candidates
            ids_to_check = []
            for g in local_results:
                if not g.last_enriched:
                    ids_to_check.append(g.f95_id)
                elif g.last_enriched:
                    # Ensure compatibility between naive DB datetimes and aware cutoff_date
                    le = g.last_enriched
                    if le.tzinfo is None:
                        le = le.replace(tzinfo=timezone.utc)

                    if le < cutoff_date:
                        ids_to_check.append(g.f95_id)

            if not ids_to_check:
                logger.info(
                    "All results are fresh per cached policy. Skipping API check."
                )
                return local_results

            logger.info(
                f"Freshness Check: {len(ids_to_check)}/{len(local_results)} items candidates for update. Scheduling background task."
            )

            # Offload to background task
            if background_tasks:
                background_tasks.add_task(
                    standalone_process_search_updates, ids_to_check
                )
            else:
                logger.warning(
                    "No background_tasks object provided. Skipping background update."
                )

            return local_results

        # 2. Remote Fallback (Only if we have a Name Query and NO results, and no creator filter which F95Z doesn't support well easily via this method)
        if query and not local_results and not creator:
            logger.info(
                f"Local miss for '{query}'. Triggering Remote Search (F95Zone)."
            )

            remote_matches = await self.f95_client.search_games(query)

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
                ts_map = await self.checker_client.check_updates(ids)

                updates_count = 0
                for game in saved_games:
                    ts = ts_map.get(game.f95_id)
                    if ts:
                        # Fetch details
                        details = await self.checker_client.get_game_details(
                            game.f95_id, ts
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
        await self.f95_client.login()

        page = 1
        has_more = True

        while has_more:
            logger.info(f"Fetching Recent Updates Page {page}...")
            updates = await self.f95_client.get_latest_updates(page=page, sort="date")

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

        timestamps = await self.checker_client.check_updates([thread_id])
        if thread_id in timestamps:
            details = await self.checker_client.get_game_details(
                thread_id, timestamps[thread_id]
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
