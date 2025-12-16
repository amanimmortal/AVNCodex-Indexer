import asyncio
from app.database import init_db, engine
from app.models import Game
from sqlmodel import select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
import os


async def main():
    print("Initializing Database...")
    await init_db()

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print("Testing persistence...")
    async with async_session() as session:
        # Check if we can write
        test_game = Game(
            id=12345, name="Test Game", author="Test Author", version="0.1"
        )
        session.add(test_game)
        try:
            await session.commit()
            print("Successfully inserted test game.")
        except Exception as e:
            await session.rollback()
            print(f"Insertion failed (might already exist): {e}")

        # Check if we can read
        result = await session.execute(select(Game).where(Game.id == 12345))
        game = result.scalar_one_or_none()
        if game:
            print(f"Read back game: {game.name} v{game.version}")
        else:
            print("Failed to read back game.")


if __name__ == "__main__":
    if not os.path.exists("data"):
        os.makedirs("data")
    asyncio.run(main())
