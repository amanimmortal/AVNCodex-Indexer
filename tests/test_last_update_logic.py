import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
from app.models import Game
from app.services.game_service import GameService
from app.services.seed_service import SeedService


@pytest.mark.asyncio
async def test_checker_update_preference(session):
    """
    Verify that _update_game_with_checker_details prefers 'last_updated' from details
    over the 'ts' argument (fast timestamp).
    """
    with (
        patch("app.services.game_service.F95ZoneClient"),
        patch("app.services.game_service.RSSClient"),
        patch("app.services.game_service.F95CheckerClient"),
    ):
        service = GameService(session)
        game = Game(f95_id=1, name="Time Test")
        session.add(game)
        await session.commit()

        # Detailed data has a SPECIFIC time X
        # Fast check passed time Y
        # We want X to be stored.

        real_update_ts = 1000000000  # 2001-09-09 ...
        fast_check_ts = 2000000000  # 2033-05-18 ... (Future/Newer staleness check)

        details = {
            "name": "Time Test",
            "last_updated": str(real_update_ts),  # Passed as string in JSON usually
        }

        # Act
        service._update_game_with_checker_details(game, details, ts=fast_check_ts)
        await session.commit()
        await session.refresh(game)

        # Assert
        assert game.f95_last_update.timestamp() == float(real_update_ts), (
            f"Should use details['last_updated'] ({real_update_ts}), not fast ts ({fast_check_ts})"
        )


@pytest.mark.asyncio
async def test_zone_date_parsing(session):
    """
    Verify that GameService.update_latest_games parses 'date' field.
    """
    # Requires mocking F95ZoneClient response
    mock_client = MagicMock()
    # Mock data from F95Zone API
    mock_client.get_latest_updates.return_value = [
        {
            "thread_id": 2,
            "title": "Zone Time Test",
            "date": 1600000000,  # 2020-09-13
        }
    ]

    with (
        patch("app.services.game_service.F95ZoneClient", return_value=mock_client),
        patch("app.services.game_service.RSSClient"),
        patch("app.services.game_service.F95CheckerClient"),
    ):
        service = GameService(session)
        # We also need to mock login
        service.f95_client.login = MagicMock()

        await service.update_latest_games()

        game = await session.get(Game, 2)
        assert game is not None
        assert game.f95_last_update is not None
        assert game.f95_last_update.timestamp() == 1600000000, (
            "Should parse 'date' from F95Zone"
        )
