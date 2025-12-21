import logging
import asyncio
from app.logging_conf import configure_logging

# Configure logging
configure_logging()
logger = logging.getLogger("test_script")


async def test_logs():
    logger.info("Starting manual verification of logging...")

    # Simulate some structured data
    logger.info("Processing item", extra={"item_id": 101, "status": "processing"})

    try:
        1 / 0
    except ZeroDivisionError:
        logger.error(
            "Simulated error for log testing",
            exc_info=True,
            extra={"context": "simulation"},
        )

    logger.warning("This is a warning", extra={"user": "test_user"})

    print("Logs generated. Check data/logs/app.json")


if __name__ == "__main__":
    asyncio.run(test_logs())
