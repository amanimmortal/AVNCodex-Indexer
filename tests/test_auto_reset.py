import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from app.services.seed_service import SeedService
from app.models import Game
import os

STATE_FILE_PATH = "seed_state_test_reset.json"


@pytest.fixture
def mock_settings():
    with patch("app.services.seed_service.STATE_FILE", STATE_FILE_PATH):
        yield


@pytest.mark.asyncio
async def test_auto_reset(mock_settings):
    # Ensure clean state
    if os.path.exists(STATE_FILE_PATH):
        os.remove(STATE_FILE_PATH)

    service = SeedService()

    # Simulate being in enrichment mode
    service.enrichment_status = "enriching"
    service.is_running = True
    service.page = 50
    service.items_processed = 5000

    # Mock DB Session to return NO candidates (simulation completion)
    with patch("app.services.seed_service.AsyncSessionLocal") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session_cls.return_value.__aenter__.return_value = mock_session

        # scalars().all() returns []
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        # Run enrichment loop
        await service.enrichment_loop()

        # Check Assertions
        assert service.is_running is False
        assert service.enrichment_status == "idle"
        assert service.page == 1
        assert service.items_processed == 0

    # Cleanup
    if os.path.exists(STATE_FILE_PATH):
        os.remove(STATE_FILE_PATH)
