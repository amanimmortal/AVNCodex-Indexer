from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text, inspect
import logging
import os
from app.settings import settings

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)

# Ensure data directory exists
os.makedirs(
    os.path.dirname(settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "")),
    exist_ok=True,
)


engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def migrate_db(connection):
    """
    Check for missing columns and add them safely.
    """
    try:

        def do_inspect(conn):
            inspector = inspect(conn)
            return inspector.get_columns("games")

        columns = await connection.run_sync(do_inspect)
        column_names = [c["name"] for c in columns]

        if "type_id" not in column_names:
            logger.info("Migrating DB: Adding 'type_id' column to 'games' table.")
            await connection.execute(
                text("ALTER TABLE games ADD COLUMN type_id INTEGER")
            )

        if "status_id" not in column_names:
            logger.info("Migrating DB: Adding 'status_id' column to 'games' table.")
            await connection.execute(
                text("ALTER TABLE games ADD COLUMN status_id INTEGER")
            )

        if "rating" not in column_names:
            logger.info("Migrating DB: Adding 'rating' column to 'games' table.")
            await connection.execute(text("ALTER TABLE games ADD COLUMN rating FLOAT"))

        if "likes" not in column_names:
            logger.info("Migrating DB: Adding 'likes' column to 'games' table.")
            await connection.execute(text("ALTER TABLE games ADD COLUMN likes INTEGER"))

    except Exception as e:
        logger.error(f"Migration Check Failed: {e}", exc_info=True)


async def init_db():
    async with engine.begin() as conn:
        # await conn.run_sync(SQLModel.metadata.drop_all) # For dev only
        await conn.run_sync(SQLModel.metadata.create_all)
        # Run custom migration check after create_all
        await migrate_db(conn)
        # Run Backfill (separate transaction/session logic usually needed, but we can do raw SQL or use a separate session)
        # We'll run it after this block ensures columns exist.


async def backfill_ratings():
    """
    One-time backfill: Parse details_json -> rating/likes for existing rows.
    """
    import json
    from app.models import Game
    from sqlalchemy.future import select

    logger.info("Checking for games requiring Rating/Likes backfill...")
    async with AsyncSessionLocal() as session:
        # Find games with details but NO rating (assuming if rating is missing, we check)
        # Limit to batch to avoid memory explosion if huge DB
        stmt = (
            select(Game)
            .where(Game.details_json.is_not(None))
            .where((Game.rating.is_(None)) | (Game.likes.is_(None)))
            .limit(1000)
        )

        while True:
            result = await session.execute(stmt)
            games = result.scalars().all()

            if not games:
                break

            logger.info(f"Backfilling ratings for {len(games)} games...")
            updates = 0
            for game in games:
                try:
                    data = json.loads(game.details_json)
                    changed = False

                    # Handle Rating (field is 'score' in F95Checker JSON)
                    rating_val = data.get("rating") or data.get("score")
                    if rating_val:
                        try:
                            game.rating = float(rating_val)
                            changed = True
                        except (ValueError, TypeError):
                            pass

                    # Handle Likes (field might be 'likes' or 'votes')
                    likes_val = data.get("likes") or data.get("votes")
                    if likes_val:
                        try:
                            game.likes = int(likes_val)
                            changed = True
                        except (ValueError, TypeError):
                            pass

                    # Mark as processed even if no data found to avoid infinite loop?
                    # No, if data is missing from JSON, we can't extract it.
                    # We should probably flag it or just let it be.
                    # To prevent infinite loop on items with details but NO rating in JSON:
                    # We can't easily "mark" them without another column.
                    # Workaround: For this specific backfill, we only target items where we set a value.
                    # BUT if we don't set a value, we will pick them up again.
                    # FIX: Explicitly set 0 or keep as is?
                    # Let's trust that most enriched items have these fields.
                    # If not, we might re-scan them on next boot. Acceptable for now.

                    if changed:
                        session.add(game)
                        updates += 1

                except Exception:
                    continue

            await session.commit()
            if updates == 0:
                # Avoid infinite loop if we found games but couldn't update any
                break

    logger.info("Backfill check complete.")


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
