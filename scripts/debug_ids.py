import asyncio
import sys
import os
import json

# Add project root to path
sys.path.append(os.getcwd())

from app.services.f95_client import F95ZoneClient
from app.services.f95checker_client import F95CheckerClient


async def main():
    game_name = "The Genesis Order"
    print(f"--- Debugging F95Zone Direct Headers for '{game_name}' ---")

    direct_client = F95ZoneClient()
    results = direct_client.search_games(game_name)

    if not results:
        print("No results found.")
        return

    # Find the one that looks like the main game
    # Genesis Order usually has high version number
    game = results[0]
    print(f"\n[Direct] Title: {game.get('title')}")
    print(f"[Direct] ID: {game.get('id')}")
    print(f"[Direct] Tags: {game.get('tags')}")
    print(f"[Direct] Prefixes: {game.get('prefixes')}")

    # Also Check raw keys
    # print(f"Raw Keys: {results[0].keys()}")


if __name__ == "__main__":
    asyncio.run(main())
