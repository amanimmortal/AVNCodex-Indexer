from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from app.database import get_session
from app.services.game_service import GameService
from app.services.seed_service import SeedService
from app.models import Game

router = APIRouter(prefix="/games", tags=["games"])
seed_service = SeedService()  # Instantiate singleton-ish service


@router.post("/seed")
async def seed_games(
    background_tasks: BackgroundTasks,
    reset: bool = Query(False, description="Reset seeding to page 1 and clear status"),
):
    """
    Trigger the alphabetical background seeding task.
    """
    # SeedService manages its own session lifecycle inside run logic
    background_tasks.add_task(seed_service.seed_loop, reset=reset)
    status_msg = "Seeding started in background"
    if reset:
        status_msg += " (Reset to Page 1)"
    return {"status": status_msg}


@router.get("/seed")
async def get_seed_status():
    """
    Get the current status of the background seeding process.
    """
    return seed_service.get_status()


@router.get("/search", response_model=List[Game])
async def search_games(
    background_tasks: BackgroundTasks,
    q: str = None,
    status: str = None,
    tags: List[str] = Query(None),
    exclude_tags: List[str] = Query(None),
    engine: int = None,
    updated_after: datetime = None,
    session: AsyncSession = Depends(get_session),
):
    service = GameService(session)
    # Use the hybrid search and index logic
    return await service.search_and_index(
        q, status, tags, exclude_tags, engine, updated_after, background_tasks
    )


@router.get("/{game_id}", response_model=Game)
async def get_game(game_id: int, session: AsyncSession = Depends(get_session)):
    service = GameService(session)
    game = await service.get_game_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return game


@router.post("/{game_id}/refresh", response_model=Game)
async def refresh_game(game_id: int, session: AsyncSession = Depends(get_session)):
    service = GameService(session)
    game = await service.force_update_game(game_id)
    if not game:
        raise HTTPException(
            status_code=404, detail="Game not found and could not be fetched remotely"
        )
    return game


@router.post("/{game_id}/track", response_model=Game)
async def track_game(game_id: int, session: AsyncSession = Depends(get_session)):
    """
    Mark a game as tracked and immediately sync its details (including downloads).
    """
    service = GameService(session)
    # track_game handles creation/fetching if missing
    game = await service.track_game(game_id)
    return game


@router.post("/{game_id}/untrack", response_model=Game)
async def untrack_game(game_id: int, session: AsyncSession = Depends(get_session)):
    """
    Stop tracking a game.
    """
    service = GameService(session)
    try:
        game = await service.untrack_game(game_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Game not found")
    return game


@router.post("/trigger-update")
async def trigger_update(session: AsyncSession = Depends(get_session)):
    """Manually trigger the daily update task."""
    service = GameService(session)
    await service.update_latest_games()
    return {"status": "update triggered"}
