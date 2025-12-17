import pytest

from app.models import Game
from app.services.seed_service import SeedService


@pytest.mark.asyncio
async def test_seed_upsert_cover_url(session):
    """
    Verify_upsert_game_basic extracts cover_url.
    """
    service = SeedService()

    # Mock data resembling F95Zone API response
    data_with_cover = {
        "thread_id": 55555,
        "title": "Seed Game",
        "creator": "Seed Dev",
        "version": "0.1",
        "cover_url": "http://example.com/seed_cover.jpg",
    }

    await service._upsert_game_basic(session, data_with_cover)
    await session.commit()

    game = await session.get(Game, 55555)
    assert game is not None
    assert game.name == "Seed Game"
    assert game.cover_url == "http://example.com/seed_cover.jpg"

    # Test update preserves existing if new is missing?
    # Actually SeedService often runs blindly, so if API returns empty it might be tricky.
    # Current logic: `or game.cover_url` -> preserves it.

    data_no_cover = {
        "thread_id": 55555,
        "title": "Seed Game Updated",
        # No cover keys
    }
    await service._upsert_game_basic(session, data_no_cover)
    await session.commit()
    await session.refresh(game)

    assert game.name == "Seed Game Updated"
    assert game.cover_url == "http://example.com/seed_cover.jpg", (
        "Should preserve existing cover"
    )
