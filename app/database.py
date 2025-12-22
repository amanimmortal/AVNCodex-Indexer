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

    except Exception as e:
        logger.error(f"Migration Check Failed: {e}", exc_info=True)


async def init_db():
    async with engine.begin() as conn:
        # await conn.run_sync(SQLModel.metadata.drop_all) # For dev only
        await conn.run_sync(SQLModel.metadata.create_all)
        # Run custom migration check after create_all
        await migrate_db(conn)


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
