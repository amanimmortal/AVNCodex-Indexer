import sys
import os

sys.path.append(os.getcwd())
import asyncio
import logging
import json
from app.services.f95_client import F95ZoneClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    client = F95ZoneClient()
    logger.info("Fetching latest updates to inspect tags...")

    # login if needed (client handles it auto usually in search/updates, but let's be explicit if fails)
    # The client.get_latest_updates attempts login.

    games = client.get_latest_updates(rows=5)

    if games:
        logger.info(f"Fetched {len(games)} games.")
        for g in games:
            logger.info(f"\nGame: {g.get('title')}")
            logger.info(f"Keys: {list(g.keys())}")

            # Check for tags
            if "tags" in g:
                logger.info(f"Tags: {g['tags']} (Type: {type(g['tags'])})")
            else:
                logger.warning("No 'tags' key found.")

            # Check prefixes (often status)
            if "prefixes" in g:
                logger.info(f"Prefixes: {g['prefixes']}")

    else:
        logger.error("No games fetched. Check login/connection.")


if __name__ == "__main__":
    main()
