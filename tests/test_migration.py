import pytest
import shutil
import os
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text, inspect
from scripts.migrate_001_add_cover_url import migrate

# Override engine in migration script?
# The script imports 'engine' from app.database.
# To test safely, we should probably patch app.database.engine or point DATABASE_URL to a test file.
# Since app.database creates engine at module level, patching is best.

from unittest.mock import patch


@pytest.mark.asyncio
async def test_migration_adds_column():
    """
    Simulate an old database state and verify migration adds column.
    """
    test_db_path = "test_migration.db"
    test_db_url = f"sqlite+aiosqlite:///{test_db_path}"

    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    # 1. Setup Old Schema (No cover_url)
    engine = create_async_engine(test_db_url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE games (f95_id INTEGER PRIMARY KEY, name TEXT, version TEXT)"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO games (f95_id, name, version) VALUES (1, 'Old Game', '0.1')"
            )
        )

    await engine.dispose()

    # 2. Run Migration using patched engine
    # We need to recreate engine to bind to new file? Or just pass it?
    # The script uses 'app.database.engine'. We need to patch it.

    new_engine = create_async_engine(test_db_url)

    with patch("scripts.migrate_001_add_cover_url.engine", new_engine):
        await migrate()

    # 3. Verify
    async with new_engine.connect() as conn:

        def verify_columns(sync_conn):
            inspector = inspect(sync_conn)
            cols = [c["name"] for c in inspector.get_columns("games")]
            return "cover_url" in cols

        has_column = await conn.run_sync(verify_columns)
        assert has_column, "Column cover_url was not added"

        # Verify data preserved
        result = await conn.execute(
            text("SELECT name, cover_url FROM games WHERE f95_id=1")
        )
        row = result.fetchone()
        assert row[0] == "Old Game"
        assert row[1] is None  # New column should be null

    await new_engine.dispose()
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
