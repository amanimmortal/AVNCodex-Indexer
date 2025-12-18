import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from app.models import Game
from app.services.game_service import GameService


@pytest.mark.asyncio
async def test_search_freshness_check_synchronous(session):
    """
    Test that search performs a SYNCHRONOUS check_updates call and updates stale games BEFORE returning.
    """
    # 1. Setup Data
    # Game 1: Fresh (recently enriched)
    fresh_date = datetime.utcnow()
    g1 = Game(
        f95_id=1,
        name="Fresh Game",
        last_enriched=fresh_date,
        f95_last_update=fresh_date,
    )

    # Game 2: Stale (enriched long ago)
    stale_date = datetime.utcnow() - timedelta(days=30)
    g2 = Game(
        f95_id=2,
        name="Stale Game",
        last_enriched=stale_date,
        f95_last_update=stale_date,
    )

    # Game 3: Never Enriched (stale by default)
    g3 = Game(f95_id=3, name="New Game", last_enriched=None, f95_last_update=stale_date)

    session.add(g1)
    session.add(g2)
    session.add(g3)
    await session.commit()

    # 2. Mock Clients
    with patch("app.services.game_service.F95CheckerClient") as MockChecker:
        checker_instance = MockChecker.return_value

        # Mock batch check: Game 1 is same time, Game 2 is NEWER, Game 3 is NEWER
        # Returns {id: timestamp}
        new_ts = datetime.utcnow().timestamp()
        wrapper_check = MagicMock(
            return_value={
                1: fresh_date.timestamp(),  # No change
                2: new_ts,  # Changed!
                3: new_ts,  # Changed!
            }
        )
        checker_instance.check_updates = wrapper_check

        # Mock full details fetch
        # Should only be called for 2 and 3
        def mock_get_details(tid, ts):
            return {
                "name": f"Updated Game {tid}",
                "version": "v2.0",
                "status": "Completed",
                "last_updated": ts,
            }

        checker_instance.get_game_details = MagicMock(side_effect=mock_get_details)

        service = GameService(session)

        # 3. Act: Search
        # We search specifically for "Game" to match all 3
        results = await service.search_and_index("Game")

        # 4. Verify
        # Should return all 3
        assert len(results) == 3

        # Verify calls
        # check_updates should be called with [1, 2, 3] (or subset if logic optimizes)
        # We expect it to check ALL returned local results to see if they are stale vs remote
        assert checker_instance.check_updates.called
        call_args = checker_instance.check_updates.call_args[0][0]
        assert set(call_args) == {1, 2, 3}

        # Verify get_game_details calls
        # Should be called for 2 and 3. NOT 1.
        # Note: get_game_details is NOT async in the client class currently based on reading,
        # but the service might wrap it in asyncio.to_thread.
        # The service calls: await asyncio.to_thread(self.checker_client.get_game_details, ...)
        # So mocking the SYNC method on the client is correct.

        assert checker_instance.get_game_details.call_count == 2

        # Verify DB Updates
        await session.refresh(g2)
        await session.refresh(g3)

        assert g2.version == "v2.0"
        assert g3.version == "v2.0"
        # Name is not updated by _update_game_with_checker_details, only by force_update_game
        # assert g2.name == "Updated Game 2"
        assert g2.status == "Completed"


@pytest.mark.asyncio
async def test_search_limit_enforced(session):
    """
    Test that search returns max 60 results.
    """
    # Create 70 games
    for i in range(70):
        g = Game(f95_id=i + 100, name=f"Bulk Game {i}", last_enriched=datetime.utcnow())
        session.add(g)
    await session.commit()

    with patch("app.services.game_service.F95CheckerClient") as MockChecker:
        checker_instance = MockChecker.return_value
        checker_instance.check_updates.return_value = {}  # No updates

        service = GameService(session)
        results = await service.search_and_index("Bulk")

        assert len(results) == 60
