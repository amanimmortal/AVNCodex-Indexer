from fastapi import FastAPI, Request
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
import asyncio
import logging
import time
from app.logging_conf import configure_logging

# Configure logging before app startup
configure_logging()
logger = logging.getLogger(__name__)

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
    logger.info("Application starting up...")
    await init_db()

    # Initialize Scheduler
    from app.settings import settings

    # Run every X hours (Configurable)
    scheduler.add_job(
        scheduled_update_task, "interval", hours=settings.SYNC_INTERVAL_HOURS
    )
    scheduler.start()

    # Check for auto-resume of seeding
    from app.routers.games import seed_service

    if seed_service.was_running_on_shutdown:
        logger.info(
            "Previous session ended with seeding active. Auto-resuming seed loop..."
        )
        asyncio.create_task(seed_service.seed_loop())

    yield
    # Shutdown
    logger.info("Application shutting down...")
    scheduler.shutdown()


app = FastAPI(title="AVNCodex Indexer", lifespan=lifespan)


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    start_time = time.time()

    # Process request
    try:
        response = await call_next(request)
        process_time = time.time() - start_time

        logger.info(
            "Incoming Request",
            extra={
                "method": request.method,
                "url": str(request.url),
                "status_code": response.status_code,
                "duration": f"{process_time:.4f}s",
                "client": request.client.host if request.client else None,
            },
        )
        return response
    except Exception as e:
        process_time = time.time() - start_time
        logger.error(
            "Request Failed",
            exc_info=True,
            extra={
                "method": request.method,
                "url": str(request.url),
                "duration": f"{process_time:.4f}s",
                "client": request.client.host if request.client else None,
            },
        )
        raise e


app.include_router(games.router)


@app.get("/")
async def root():
    return {"message": "AVNCodex Indexer is running"}
