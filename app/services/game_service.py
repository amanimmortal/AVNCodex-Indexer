import logging
import json
import asyncio
from datetime import datetime
from typing import List, Optional
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import BackgroundTasks
from app.models import Game
from app.services.f95_client import F95ZoneClient
from app.services.rss_client import RSSClient
from app.services.f95checker_client import F95CheckerClient
from app.database import AsyncSessionLocal

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
                    self._update_game_with_checker_details(game, details, ts)
                    count += 1

        await self.session.commit()
        logger.info(f"Synced {count} tracked games.")

    def _update_game_with_checker_details(self, game: Game, details: dict, ts: int):
        """
        Merge F95Checker details into game object.
        """
        game.version = details.get("version") or game.version
        game.status = str(details.get("status"))

        game.f95_last_update = datetime.fromtimestamp(ts)
        game.last_updated_at = datetime.utcnow()
        game.last_enriched = datetime.utcnow()

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
        updated_after: datetime = None,
        background_tasks: BackgroundTasks = None,
    ) -> List[Game]:
        """
        Refactored Search Logic (Local First with Remote Fallback).
        """
        # 1. Local Search (Priority)
        stmt = select(Game)
        if query:
            stmt = stmt.where(Game.name.ilike(f"%{query}%"))

        if status:
            stmt = stmt.where(Game.status == status)

        if tags:
            for tag in tags:
                stmt = stmt.where(Game.tags.contains(tag))

        if updated_after:
            stmt = stmt.where(Game.f95_last_update >= updated_after)

        result = await self.session.execute(stmt)
        local_results = result.scalars().all()

        if local_results:
            logger.info(f"Local hit: {len(local_results)} matches.")

            # Check Staleness
            if background_tasks:
                now = datetime.utcnow()
                for game in local_results:
                    if game.tracked:
                        continue

                    is_stale = False
                    if not game.last_enriched:
                        is_stale = True
                    elif (now - game.last_enriched).days > 7:
                        is_stale = True

                    if is_stale:
                        logger.info(
                            f"Game {game.f95_id} is stale / not enriched. Scheduling background update."
                        )
                        background_tasks.add_task(standalone_force_update, game.f95_id)

            return local_results

        # 2. Remote Fallback (Only if we have a Name Query and NO results)
        if query and not local_results:
            logger.info(
                f"Local miss for '{query}'. Triggering Remote Search (F95Zone)."
            )

            remote_matches = await asyncio.to_thread(
                self.f95_client.search_games, query
            )

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
                # Attempt to get cover if available in search result
                # Note: F95Zone Latest Updates API often has 'icon' or similar, but maybe not full cover.
                # We check whatever keys are present.
                game.cover_url = (
                    data.get("cover_url")
                    or data.get("featured_image")
                    or data.get("image_url")
                    or data.get("cover")
                    or game.cover_url
                )
                # Do not overwrite status/tags from zone search

                self.session.add(game)
                saved_games.append(game)

            await self.session.commit()
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

                # Check date vs known? Simple upsert for now unless logic refines.
                # game.f95_last_update = ...

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
                game.tags = json.dumps(details.get("tags") or [])
                game.details_json = json.dumps(details)
                game.last_enriched = datetime.utcnow()
                game.f95_last_update = datetime.fromtimestamp(timestamps[thread_id])

                self.session.add(game)
                await self.session.commit()
                await self.session.refresh(game)

        return game
