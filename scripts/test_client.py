import asyncio
import logging
from app.services.f95_client import F95ZoneClient

logging.basicConfig(level=logging.INFO)


def main():
    client = F95ZoneClient()
    print(f"Testing client with User: {client.username}")

    # Test Login
    if client.login():
        print("Login Successful!")
    else:
        print(
            "Login Failed (Check credentials or 2FA). Proceeding with public access test."
        )

    # Test Get Updates
    updates = client.get_latest_updates(rows=5)
    print(f"Fetched {len(updates)} updates.")
    for game in updates:
        print(f"- {game.get('title')} (Thread: {game.get('thread_id')})")

    # Test Search
    query = "Eternum"
    print(f"\nSearching for '{query}'...")
    results = client.search_games(query)
    print(f"Found {len(results)} matches.")
    for game in results:
        print(f"- {game.get('title')} by {game.get('creator')}")


if __name__ == "__main__":
    main()
