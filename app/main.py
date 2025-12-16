from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.database import init_db
from app.routers import games
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# We need to import models so SQLModel knows about them before init_db
from app.models import Game  # noqa: F401
from app.services.game_service import GameService
from sqlalchemy.orm import sessionmaker
from app.database import engine
from sqlalchemy.ext.asyncio import AsyncSession

scheduler = AsyncIOScheduler()


async def scheduled_update_task():
    # Create a new session for the background task
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        service = GameService(session)
        await service.update_latest_games()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()

    # Initialize Scheduler
    from app.settings import settings

    # Run every X hours (Configurable)
    scheduler.add_job(
        scheduled_update_task, "interval", hours=settings.SYNC_INTERVAL_HOURS
    )
    scheduler.start()

    yield
    # Shutdown
    scheduler.shutdown()


app = FastAPI(title="AVNCodex Indexer", lifespan=lifespan)

app.include_router(games.router)


@app.get("/")
async def root():
    return {"message": "AVNCodex Indexer is running"}
