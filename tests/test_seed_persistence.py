import pytest
import os

from unittest.mock import MagicMock, patch, AsyncMock
from app.services.seed_service import SeedService

STATE_FILE_PATH = "seed_state_test.json"


@pytest.fixture
def mock_settings():
    with patch("app.services.seed_service.STATE_FILE", STATE_FILE_PATH):
        yield


@pytest.mark.asyncio
async def test_state_persistence(mock_settings):
    # Ensure clean state
    if os.path.exists(STATE_FILE_PATH):
        os.remove(STATE_FILE_PATH)

    service = SeedService()

    # Modify state
    service.page = 42
    service.items_processed = 100
    service.enrichment_status = "enriching"
    service.is_running = True

    # Save
    service._save_state()

    # Reload in new instance
    new_service = SeedService()
    assert new_service.page == 42
    assert new_service.items_processed == 100
    assert new_service.enrichment_status == "enriching"
    assert new_service.was_running_on_shutdown is True

    # Cleanup
    if os.path.exists(STATE_FILE_PATH):
        os.remove(STATE_FILE_PATH)


@pytest.mark.asyncio
async def test_reset_logic(mock_settings):
    # Ensure clean state
    if os.path.exists(STATE_FILE_PATH):
        os.remove(STATE_FILE_PATH)

    service = SeedService()
    service.page = 99
    service.enrichment_status = "enriching"
    service._save_state()

    # Create logic mock to avoid real API calls
    service.client = MagicMock()
    service.checker_client = MagicMock()

    import inspect

    print(f"DEBUG SIGNATURE: {inspect.signature(service.seed_loop)}")
    # Run seed_loop with reset=True
    # We mock seed_loop internals to avoid infinite loops or network calls,
    # but we can rely on the fact that reset happens BEFORE loop starts.
    # Actually, we can just inspect the state after calling seed_loop with a mocked loop helper?
    # Or just run it and throw an exception immediately to stop it.

    with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
        # Cause logic to "crash" or return immediately to stop infinite loop
        # First call is login
        # Second call is get_latest_updates
        service.is_running = False  # Reset running state

        # We need to interrupt it.
        mock_thread.side_effect = Exception("Stop Loop")

        await service.seed_loop(reset=True)

        # Check if reset happened
        # We expect page to be 1 (reset happens before calls)
        # However, due to exception, it might not save the final stopped state as 1 if we are not careful?
        # The reset block saves state immediately.

    # Reload to verify file content
    new_service = SeedService()
    assert new_service.page == 1
    assert new_service.items_processed == 0
    assert (
        new_service.enrichment_status == "idle"
    )  # It should reset to idle, then loop sets it to seeding

    # Cleanup
    if os.path.exists(STATE_FILE_PATH):
        os.remove(STATE_FILE_PATH)
