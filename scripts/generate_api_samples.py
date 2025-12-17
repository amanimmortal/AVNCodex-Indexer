import asyncio
import sys
import os
import json

# Add project root to path
sys.path.append(os.getcwd())

from app.services.f95_client import F95ZoneClient
from app.services.f95checker_client import F95CheckerClient


async def main():
    print("--- Generating API Data Samples ---")

    # 1. Get a fresh game from F95Zone (Direct)
    # matching the user's advice to use 158858 (The Genesis Order) if possible,
    # but falling back to latest if search fails.
    target_id = 158858
    direct_game_data = None
    checker_game_data = None

    direct_client = F95ZoneClient()
    checker_client = F95CheckerClient()

    # Try to find specific game first
    print(f"Attempting to fetch data for ID {target_id}...")

    # For F95Checker, we can go by ID directly
    ts_map = checker_client.check_updates([target_id])
    if target_id in ts_map:
        checker_game_data = checker_client.get_game_details(
            target_id, ts_map[target_id]
        )

    # For F95Zone, we need to find it.
    # If login fails, search might return empty.
    # Let's try 'latest_updates' and see if we can just pick ANY game if that fails?
    # User asked for "The Genesis Order" ideally or "the same game".

    # Let's try to search by name from checker data if available
    search_name = "The Genesis Order"
    if checker_game_data and checker_game_data.get("name"):
        # F95Checker name might be 'The Genesis Order' or something.
        # But previous debug showed '-u4ia-' which is weird.
        # Let's trust the hardcoded name "The Genesis Order" for search first.
        pass

    results = direct_client.search_games(search_name)
    if results:
        # look for ID match
        for res in results:
            rid = res.get("id") or res.get("thread_id")
            if rid and int(rid) == target_id:
                direct_game_data = res
                break
        if not direct_game_data and results:
            # Fallback: just take the first result if it matches name roughly?
            # Or keep searching.
            pass

    # If we still don't have direct data (e.g. login issue),
    # let's grab the LATEST game from get_latest_updates()
    # and then fetch that specific ID from Checker.
    if not direct_game_data:
        print(
            "Could not find target game in F95Zone (login/search issue). Falling back to 'Latest'..."
        )
        updates = direct_client.get_latest_updates(rows=1)
        if updates:
            direct_game_data = updates[0]
            # Now update the target ID to match this game
            target_id = int(
                direct_game_data.get("id") or direct_game_data.get("thread_id")
            )
            print(f"New Target ID: {target_id} ({direct_game_data.get('title')})")

            # Re-fetch Checker data for this new ID
            ts_map = checker_client.check_updates([target_id])
            if target_id in ts_map:
                checker_game_data = checker_client.get_game_details(
                    target_id, ts_map[target_id]
                )
            else:
                checker_game_data = {"error": "Game not found in F95Checker"}
        else:
            print("Failed to fetch any games from F95Zone.")
            return

    # Output to markdown file
    output_path = r"d:\GitHub\AVNCodex-Indexer\docs\API_DATA_SAMPLES.md"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# API Data Samples for Game ID: {target_id}\n\n")

        f.write(f"## F95Zone (Direct API)\n")
        f.write("```json\n")
        f.write(
            json.dumps(direct_game_data, indent=2, ensure_ascii=False)
            if direct_game_data
            else "No Data"
        )
        f.write("\n```\n\n")

        f.write(f"## F95Checker API\n")
        f.write("```json\n")
        f.write(
            json.dumps(checker_game_data, indent=2, ensure_ascii=False)
            if checker_game_data
            else "No Data"
        )
        f.write("\n```\n")

    print(f"Data samples saved to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
