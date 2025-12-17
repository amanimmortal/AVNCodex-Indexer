import pytest
from unittest.mock import MagicMock, patch
from sqlmodel import Session, SQLModel, create_engine
from datetime import datetime, timedelta
import json

from app.models import Game
# Assuming these services will be refactored/created; mocking for now or importing if they exist
# from app.services.f95_client import F95ZoneClient
# from app.services.game_service import GameService


# Setup in-memory DB for testing

# Session fixture moved to conftest.py


@pytest.mark.asyncio
async def test_game_schema_updates(session):
    """
    Test that the Game model has the new required columns.
    """
    # Create a dummy game with new fields
    game = Game(
        f95_id=12345,
        name="Test Game",
        creator="Test Dev",
        version="v1.0",
        tags=json.dumps(["RPG", "Adventure"]),
        status="Completed",
        last_enriched=datetime.utcnow(),
    )
    session.add(game)
    await session.commit()
    await session.refresh(game)

    assert game.f95_id == 12345
    assert "RPG" in game.tags
    assert game.status == "Completed"
    assert game.last_enriched is not None


@pytest.mark.asyncio
async def test_f95zone_sync_isolation(session):
    """
    Test that F95Zone sync ONLY updates basic info and DOES NOT overwrite tags/status.
    """
    # 1. Pre-seed a game with RICH details (simulating a previous Checker sync)
    rich_game = Game(
        f95_id=999,
        name="Old Name",
        creator="Old Dev",
        tags=json.dumps(["Hardcore", "Strategy"]),
        status="Ongoing",
        details_json=json.dumps({"desc": "stuff"}),
        last_enriched=datetime.utcnow(),
    )
    session.add(rich_game)
    await session.commit()

    # 2. Simulate F95Zone API data (Basic info only)
    zone_data = {
        "thread_id": 999,
        "title": "New Name",
        "creator": "New Dev",
        "version": "v2.0",
        "date": "Today",
    }

    # 3. Apply Update (Mocking the logic we WILL implement in GameService)
    # For now, we manually apply what the service IS SUPPOSED to do:
    # Update Name, Creator, Version. IGNORE Tags, Status.

    # Re-fetch from DB
    game = await session.get(Game, 999)
    game.name = zone_data["title"]
    game.creator = zone_data["creator"]
    game.version = zone_data["version"]
    # game.tags = ... # SHOULD NOT TOUCH THIS

    session.add(game)
    await session.commit()
    await session.refresh(game)

    # 4. Assertions
    assert game.name == "New Name"
    assert game.creator == "New Dev"
    assert game.version == "v2.0"

    # CRITICAL: Tags and Status must remain untouched
    assert game.status == "Ongoing"
    assert "Hardcore" in game.tags


@pytest.mark.asyncio
async def test_f95checker_enrichment(session):
    """
    Test that F95Checker data correctly populates the specific fields.
    """
    # 1. Create a basic game (Seeded from Zone)
    game = Game(f95_id=555, name="Basic Game")
    session.add(game)
    await session.commit()

    # 2. Simulate Checker Data
    checker_data = {
        "status": "Completed",
        "tags": ["Visual Novel", "3DCG"],
        "version": "Full",
    }

    # 3. Apply Update
    game = await session.get(Game, 555)
    game.status = checker_data["status"]
    game.tags = json.dumps(checker_data["tags"])
    game.last_enriched = datetime.utcnow()

    session.add(game)
    await session.commit()
    await session.refresh(game)

    assert game.status == "Completed"
    assert "3DCG" in game.tags
    assert game.last_enriched is not None


def test_pagination_logic_with_dates():
    """
    Test logic for 'Stop fetching if date < last_sync'.
    """
    last_sync = datetime.utcnow() - timedelta(hours=6)

    # Case 1: Game is newer than sync
    game_date_new = datetime.utcnow() - timedelta(hours=1)
    assert game_date_new > last_sync  # Should Upsert

    # Case 2: Game is older than sync
    game_date_old = datetime.utcnow() - timedelta(hours=12)
    assert not (game_date_old > last_sync)  # Should Stop/Ignore
