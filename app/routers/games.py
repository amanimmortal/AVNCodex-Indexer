from fastapi import APIRouter, Depends, HTTPException
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.services.game_service import GameService
from app.models import Game

router = APIRouter(prefix="/games", tags=["games"])


@router.get("/search", response_model=List[Game])
async def search_games(q: str, session: AsyncSession = Depends(get_session)):
    service = GameService(session)
    # Use the hybrid search and index logic
    return await service.search_and_index(q)


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


@router.post("/trigger-update")
async def trigger_update(session: AsyncSession = Depends(get_session)):
    """Manually trigger the daily update task."""
    service = GameService(session)
    await service.update_latest_games()
    return {"status": "update triggered"}
