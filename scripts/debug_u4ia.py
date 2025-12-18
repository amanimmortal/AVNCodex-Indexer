import asyncio
import os
import sys
from datetime import datetime

# Add parent to path
sys.path.append(os.getcwd())

from app.services.f95_client import F95ZoneClient
from app.services.f95checker_client import F95CheckerClient


async def main():
    print("--- Inspecting 'u4ia' Data ---")

    # 1. Check F95Zone Search
    print("\n[F95Zone Search]")
    z_client = F95ZoneClient()
    try:
        z_client.login()
    except:
        print("Login failed, continuing...")

    z_results = await asyncio.to_thread(z_client.search_games, "u4ia")
    target_game = None
    for res in z_results:
        # Loose match for debug
        if "u4ia" in res.get("title", "").lower():
            target_game = res
            print(f"Found Match: {res.get('title')}")
            break

    if target_game:
        print("Keys:", list(target_game.keys()))
        print(f"ts: {target_game.get('ts')}")
        print(f"date: {target_game.get('date')}")
        tid = target_game.get("thread_id") or target_game.get("id")
    else:
        print("No F95Zone match found.")
        tid = None

    if not tid:
        print("Cannot proceed to Checker check without Thread ID.")
        return

    tid = int(tid)
    print(f"\n[F95Checker Data] Thread ID: {tid}")
    c_client = F95CheckerClient()

    # 2. Check Fast Endpoint
    timestamps = c_client.check_updates([tid])
    fast_ts = timestamps.get(tid)
    print(
        f"Fast Check TS: {fast_ts} -> {datetime.fromtimestamp(fast_ts) if fast_ts else 'None'}"
    )

    if fast_ts:
        # 3. Check Full Details
        details = c_client.get_game_details(tid, fast_ts)
        if details:
            print("Full Details Keys:", list(details.keys()))
            print(f"last_updated: {details.get('last_updated')}")
            if details.get("last_updated"):
                print(
                    f"Converted: {datetime.fromtimestamp(float(details['last_updated']))}"
                )

            print(f"status: {details.get('status')}")
            print(f"version: {details.get('version')}")


if __name__ == "__main__":
    asyncio.run(main())
