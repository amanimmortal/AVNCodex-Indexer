import asyncio
import os
import sys

sys.path.append(os.getcwd())
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///reference_lib/data/avn_index.db"

from app.database import AsyncSessionLocal
from app.models import Game
from sqlalchemy.future import select


async def inspect_json():
    async with AsyncSessionLocal() as session:
        # Check specific ID requested by user
        stmt = select(Game).where(Game.f95_id == 158858)
        result = await session.execute(stmt)
        game = result.scalar_one_or_none()

        if game:
            print(f"F95 ID: {game.f95_id}")
            print(f"Is Rating Column NULL? {game.rating is None}")
            print(f"Is Likes Column NULL? {game.likes is None}")
            print(f"JSON Content:\n{game.details_json}")

            import json

            try:
                data = json.loads(game.details_json)
                print(f"Key 'rating' in JSON? {'rating' in data}")
                if "rating" in data:
                    print(f"Value: {data['rating']}")

                print(f"Key 'likes' in JSON? {'likes' in data}")
                if "likes" in data:
                    print(f"Value: {data['likes']}")
            except Exception as e:
                print(f"JSON Parse Error: {e}")
        else:
            print("Game 158858 not found.")


if __name__ == "__main__":
    asyncio.run(inspect_json())
