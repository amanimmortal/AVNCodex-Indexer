import asyncio
import logging
import json
import sys
import os

# Ensure app is in path
sys.path.append(os.getcwd())

from app.services.rss_client import RSSClient
from app.services.f95_client import F95ZoneClient
from app.services.f95checker_client import F95CheckerClient

# Configure Logging to console
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("VERIFIER")


async def verify_rss():
    logger.info("--- 1. Testing RSSClient ---")
    client = RSSClient()
    games = await client.get_games(limit=5)

    if games:
        logger.info(f"✅ RSS Success. Fetched {len(games)} items.")
        logger.info(f"Sample: {games[0]['name']} (ID: {games[0]['id']})")
    else:
        logger.error("❌ RSS Failed or Empty.")


async def verify_f95zone():
    logger.info("\n--- 2. Testing F95ZoneClient ---")
    client = F95ZoneClient()

    # Login
    logger.info("Attempting Login...")
    success = await client.login()
    if success:
        logger.info("✅ Login Success.")
    else:
        logger.warning(
            "⚠️ Login Failed (Check Creds). Proceeding anonymously if possible."
        )

    # Search
    query = "Eternum"
    logger.info(f"Searching for '{query}'...")
    results = await client.search_games(query)
    if results:
        logger.info(f"✅ Search Success. Found {len(results)} matches.")
        logger.info(f"Sample: {results[0]['title']} (ID: {results[0]['thread_id']})")
    else:
        logger.error("❌ Search Failed or No Results.")

    await client.close()


async def verify_f95checker():
    logger.info("\n--- 3. Testing F95CheckerClient ---")
    client = F95CheckerClient()

    # Known ID (Eternum usually has ID around these, let's allow dynamic if possible,
    # but for stable test let's use a known big game ID if we had one.
    # Let's use correct ID for Eternum: 135500 (approx) or just pick one from previous steps if possible?
    # Better: Use a hardcoded known ID for a popular game.
    # 'Being a DIK': 15306, 'Eternum': 199960 (check actual id via search in future? No, just guess specific one or use one from RSS)

    # For now, let's try a list of random IDs that likely exist or recently updated ones from RSS?
    # Actually, let's use a known stable ID.
    # ID: 15306 (Being a DIK) is a classic.
    test_ids = [15306]

    logger.info(f"Checking updates for IDs: {test_ids}")
    timestamps = await client.check_updates(test_ids)

    if timestamps:
        logger.info(f"✅ Fast Check Success. Results: {timestamps}")

        tid = list(timestamps.keys())[0]
        ts = timestamps[tid]

        logger.info(f"Fetching full details for {tid}...")
        details = await client.get_game_details(tid, ts)

        if details:
            logger.info("✅ Full Details Success.")
            logger.info(f"Name: {details.get('name')}")
            logger.info(f"Version: {details.get('version')}")
            # Check for critical fields
            if "downloads" in details:
                logger.info(
                    f"✅ Downloads field present ({len(details['downloads'])} platforms)."
                )
            else:
                logger.warning("⚠️ 'downloads' field missing!")
        else:
            logger.error("❌ Full Details Failed.")

    else:
        logger.error("❌ Fast Check Failed (or game not found).")

    await client.close()


async def main():
    logger.info("STARTING REAL WORLD API VERIFICATION")
    try:
        await verify_rss()
        await verify_f95zone()
        await verify_f95checker()
    except Exception as e:
        logger.exception("CRITICAL FAILURE IN VERIFICATION SCRIPT")
    finally:
        logger.info("VERIFICATION COMPLETE")


if __name__ == "__main__":
    asyncio.run(main())
