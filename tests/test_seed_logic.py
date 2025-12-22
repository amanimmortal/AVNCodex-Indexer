import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.seed_service import SeedService
from app.models import Game
from datetime import datetime


@pytest.mark.asyncio
async def test_enrichment_loop_logic():
    # Mock dependencies
    with (
        patch("app.services.seed_service.F95ZoneClient") as mock_f95_client,
        patch("app.services.seed_service.F95CheckerClient") as mock_checker_client,
        patch("app.services.seed_service.AsyncSessionLocal") as mock_session_cls,
        patch("app.services.seed_service.GameService") as mock_game_service_cls,
    ):
        # Setup Mock Instances
        mock_checker = mock_checker_client.return_value
        mock_session = AsyncMock()
        mock_session_cls.return_value.__aenter__.return_value = mock_session

        mock_game_service = mock_game_service_cls.return_value

        # Initialize Service
        service = SeedService()

        # Test Data
        game1 = Game(f95_id=1, name="Game 1")
        game2 = Game(f95_id=2, name="Game 2")

        # Mock Session Execute for Candidates
        # 1st call: Returns [game1, game2]
        # 2nd call: Returns [] (to stop loop)
        mock_result1 = MagicMock()
        mock_result1.scalars.return_value.all.return_value = [game1, game2]

        mock_result2 = MagicMock()
        mock_result2.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [mock_result1, mock_result2]

        # Mock Check Updates (Fast Check)
        mock_checker.check_updates.return_value = {1: 1000, 2: 2000}

        # Mock Get Details (Full Details)
        mock_checker.get_game_details.side_effect = [
            {"name": "Game 1 Detail"},  # For Game 1
            {"name": "Game 2 Detail"},  # For Game 2
        ]

        # Force is_running = True
        service.is_running = True

        # Run Enrichment Loop (We need to break the infinite loop if our logic fails to break)
        # However, our mock setup returns empty candidates on 2nd iteration, which should break it.
        # But wait, logic breaks on "logging no more games".
        # We also need to mock asyncio.sleep to avoid waiting real time
        with patch("asyncio.sleep", AsyncMock()) as mock_sleep:
            await service.enrichment_loop()

        # Assertions

        # 1. Did we call check_updates?
        mock_checker.check_updates.assert_called()

        # 2. Did we call get_game_details for both?
        assert mock_checker.get_game_details.call_count == 2

        # 3. Did we call update_game_with_checker_details?
        assert mock_game_service.update_game_with_checker_details.call_count == 2

        # 4. Status Check
        # Should remain 'enriching' inside logic, but loop breaks when no candidates.
        # We can check logs if we captured them, but asserts on mocks are good enough.
