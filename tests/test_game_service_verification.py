import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from app.models import Game
from app.services.game_service import GameService
from fastapi import BackgroundTasks


@pytest.mark.asyncio
async def test_staleness_checks(session):
    """
    Verify that old games trigger a background update task.
    """
    # 1. Setup Stale Game
    stale_date = datetime.utcnow() - timedelta(days=10)
    game = Game(
        f95_id=99999,
        name="Stale Game",
        last_enriched=stale_date,
        f95_last_update=stale_date,
    )
    session.add(game)
    await session.commit()

    # 2. Mock Dependencies
    with (
        patch("app.services.game_service.F95ZoneClient"),
        patch("app.services.game_service.RSSClient"),
        patch("app.services.game_service.F95CheckerClient"),
    ):
        service = GameService(session)
        tasks = MagicMock(spec=BackgroundTasks)

        # 3. Act: Search matching the game
        # Query "Stale" matches "Stale Game" via ilike
        results = await service.search_and_index("Stale", background_tasks=tasks)

        # 4. Assert
        assert len(results) == 1
        assert results[0].f95_id == 99999

        # Should have triggered task
        assert tasks.add_task.called, "Background task should be called for stale game"

        # Check argument
        args, _ = tasks.add_task.call_args
        # First arg is function, second is 99999
        assert args[1] == 99999


@pytest.mark.asyncio
async def test_fresh_game_no_update(session):
    """
    Verify that fresh games DO NOT trigger background update.
    """
    fresh_date = datetime.utcnow() - timedelta(days=1)
    game = Game(f95_id=88888, name="Fresh Game", last_enriched=fresh_date)
    session.add(game)
    await session.commit()

    with (
        patch("app.services.game_service.F95ZoneClient"),
        patch("app.services.game_service.RSSClient"),
        patch("app.services.game_service.F95CheckerClient"),
    ):
        service = GameService(session)
        tasks = MagicMock(spec=BackgroundTasks)

        results = await service.search_and_index("Fresh", background_tasks=tasks)

        assert len(results) == 1
        assert not tasks.add_task.called, "Should not trigger update for fresh game"
