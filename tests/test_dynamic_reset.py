import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from app.services.seed_service import SeedService
import os

STATE_FILE_PATH = "seed_state_test_dynamic.json"


@pytest.fixture
def mock_settings():
    with patch("app.services.seed_service.STATE_FILE", STATE_FILE_PATH):
        yield


@pytest.mark.asyncio
async def test_dynamic_reset(mock_settings):
    # Ensure clean state
    if os.path.exists(STATE_FILE_PATH):
        os.remove(STATE_FILE_PATH)

    service = SeedService()
    service.is_running = True  # Simulate running
    service.page = 500

    # Call reset while running
    # This should NOT start a new loop (returns early) but SHOULD update state
    await service.seed_loop(reset=True)

    # Verify state updated
    assert service.page == 1
    assert service.items_processed == 0
    assert service.enrichment_status == "idle"

    # Verify it saved
    new_service = SeedService()
    assert new_service.page == 1

    # Cleanup
    if os.path.exists(STATE_FILE_PATH):
        os.remove(STATE_FILE_PATH)
