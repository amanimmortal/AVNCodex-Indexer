import pytest
import json
import os
from unittest.mock import patch
from app.services.seed_service import SeedService


# Helper to create a temp state file
@pytest.fixture
def temp_state_file(tmp_path):
    file_path = tmp_path / "seed_state.json"
    return str(file_path)


@pytest.mark.asyncio
async def test_seed_service_loads_running_state(temp_state_file):
    """
    Test that SeedService correctly detects if it was running from the state file.
    """
    # 1. Create state file saying "is_running": true
    with open(temp_state_file, "w") as f:
        json.dump({"page": 5, "items_processed": 100, "is_running": True}, f)

    # 2. Patch STATE_FILE in the module
    with patch("app.services.seed_service.STATE_FILE", temp_state_file):
        # 3. Instantiate Service
        service = SeedService()

        # 4. Assert
        assert service.page == 5
        assert service.items_processed == 100
        assert service.was_running_on_shutdown is True
        # But valid current state is not running yet
        assert service.is_running is False


@pytest.mark.asyncio
async def test_seed_service_saves_running_state(temp_state_file):
    """
    Test that SeedService updates the file to is_running=True when loop starts
    and False when it ends.
    """
    if os.path.exists(temp_state_file):
        os.remove(temp_state_file)

    with (
        patch("app.services.seed_service.STATE_FILE", temp_state_file),
        patch("app.services.seed_service.F95ZoneClient") as MockClient,
    ):
        service = SeedService()
        mock_client_instance = MockClient()
        # Initial return value for first run
        mock_client_instance.get_latest_updates.return_value = []

        with patch(
            "app.services.seed_service.AsyncSessionLocal",
            side_effect=TypeError("Don't touch DB"),
        ):
            # 1. Verify "Running -> Stopped" flow
            await service.seed_loop()

            with open(temp_state_file, "r") as f:
                data = json.load(f)
                assert data["is_running"] is False

            # 2. Verify "Running" state during loop
            # We define a sync function because to_thread runs sync code
            def check_file_while_running(**kwargs):
                with open(temp_state_file, "r") as f:
                    d = json.load(f)
                    if not d.get("is_running"):
                        raise ValueError("File says NOT running during loop!")
                return []  # Return empty to break loop naturally

            mock_client_instance.get_latest_updates.side_effect = (
                check_file_while_running
            )

            # Reset running state internal check if needed (it is false now)
            await service.seed_loop()
            # If we get here without exception, success
