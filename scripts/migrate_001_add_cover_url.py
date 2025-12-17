import asyncio
import logging
from sqlalchemy import inspect, text
import sys
import os

# Add parent directory to path so we can import 'app'
sys.path.append(os.getcwd())

from app.database import engine

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migration")


async def migrate():
    """
    Adds cover_url column to games table if it doesn't exist.
    """
    logger.info("Starting migration: 001_add_cover_url")

    async with engine.connect() as conn:

        def check_and_upgrade(sync_conn):
            inspector = inspect(sync_conn)
            if not inspector.has_table("games"):
                logger.info("Table 'games' does not exist. Skipping migration.")
                return

            columns = [c["name"] for c in inspector.get_columns("games")]

            if "cover_url" not in columns:
                logger.info("Column 'cover_url' missing. Adding it...")
                try:
                    sync_conn.execute(
                        text("ALTER TABLE games ADD COLUMN cover_url TEXT")
                    )
                    logger.info("Column 'cover_url' added successfully.")
                except Exception as e:
                    logger.error(f"Failed to add column: {e}")
                    raise
            else:
                logger.info("Column 'cover_url' already exists. Skipping.")

        await conn.run_sync(check_and_upgrade)
        await conn.commit()

    logger.info("Migration complete.")


if __name__ == "__main__":
    asyncio.run(migrate())
