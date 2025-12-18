import pytest
from unittest.mock import MagicMock, patch
from app.models import Game
from app.services.game_service import GameService


@pytest.mark.asyncio
async def test_cover_url_extraction(session):
    """
    Verify that cover_url is correctly extracted from API responses.
    """
    # 1. Setup Service with Mocks
    with (
        patch("app.services.game_service.F95ZoneClient"),
        patch("app.services.game_service.RSSClient"),
        patch("app.services.game_service.F95CheckerClient"),
    ):
        service = GameService(session)

        # 2. Test F95Checker Detail Update
        # Simulate a game and incoming checker details
        game = Game(f95_id=100, name="Test Game")
        session.add(game)
        await session.commit()

        details_with_cover = {
            "name": "Test Game",
            "version": "1.0",
            "status": "Completed",
            "featured_image": "http://example.com/cover1.jpg",  # Primary key check
        }

        service._update_game_with_checker_details(game, details_with_cover, 1234567890)
        await session.commit()
        await session.refresh(game)

        assert game.cover_url == "http://example.com/cover1.jpg", (
            "Should extract 'featured_image' as cover_url"
        )

        # 3. Test Fallback Keys
        details_secondary = {
            "name": "Test Game 2",
            "image_url": "http://example.com/cover2.jpg",  # Secondary key check
        }
        game2 = Game(f95_id=101, name="Test Game 2")
        session.add(game2)
        await session.commit()

        service._update_game_with_checker_details(game2, details_secondary, 1234567890)
        await session.commit()
        await session.refresh(game2)

        assert game2.cover_url == "http://example.com/cover2.jpg", (
            "Should extract 'image_url' as cover_url"
        )

        # 4. Test Persistence (Don't overwrite with None)
        details_empty = {
            "name": "Test Game",
            # No image keys
        }
        service._update_game_with_checker_details(game, details_empty, 1234567892)
        await session.commit()
        await session.refresh(game)

        assert game.cover_url == "http://example.com/cover1.jpg", (
            "Should preserve existing cover_url if new one is missing"
        )


@pytest.mark.asyncio
async def test_null_cover_is_updated(session):
    """
    Verify that if DB has NULL cover, an incoming sync updates it.
    """
    with (
        patch("app.services.game_service.F95ZoneClient"),
        patch("app.services.game_service.RSSClient"),
        patch("app.services.game_service.F95CheckerClient"),
    ):
        service = GameService(session)

        # 1. Start with NULL cover
        game = Game(f95_id=999, name="Null Cover Game", cover_url=None)
        session.add(game)
        await session.commit()

        # 2. Sync with new data containing cover
        details_new = {
            "name": "Null Cover Game",
            "featured_image": "http://example.com/new_cover.jpg",
        }
        service._update_game_with_checker_details(game, details_new, 123456)
        await session.commit()
        await session.refresh(game)

        # 3. Assert it updated
        assert game.cover_url == "http://example.com/new_cover.jpg", (
            "NULL cover should be updated by new data"
        )
