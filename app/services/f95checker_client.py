import requests
import logging
from typing import List, Dict, Any, Optional
from app.settings import settings

logger = logging.getLogger(__name__)


class F95CheckerClient:
    BASE_URL = "https://api.f95checker.dev"

    def __init__(self):
        self.session = requests.Session()
        self.daily_limit = settings.F95CHECKER_DAILY_LIMIT

    def check_updates(self, thread_ids: List[int]) -> Dict[int, int]:
        """
        Bulk check for updates. Returns {thread_id: last_changed_timestamp}.
        """
        ids_str = ",".join(map(str, thread_ids))
        url = f"{self.BASE_URL}/fast"

        logger.info(
            "Calling F95Checker Fast Check",
            extra={
                "url": url,
                "count": len(thread_ids),
                "ids_preview": thread_ids[:5] if len(thread_ids) > 5 else thread_ids,
            },
        )

        try:
            resp = self.session.get(url, params={"ids": ids_str})
            resp.raise_for_status()

            data = resp.json()
            logger.info(
                "F95Checker Fast Check Success",
                extra={"status_code": resp.status_code, "response_count": len(data)},
            )
            return {int(k): v for k, v in data.items()}
        except Exception as e:
            logger.error(
                "F95Checker fast check failed",
                exc_info=True,
                extra={"url": url, "error": str(e)},
            )
            return {}

    def get_game_details(
        self, thread_id: int, timestamp: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get full details. Requires timestamp from fast check.
        """
        url = f"{self.BASE_URL}/full/{thread_id}"
        logger.info(
            "Calling F95Checker Full Details",
            extra={"url": url, "thread_id": thread_id, "timestamp": timestamp},
        )

        try:
            resp = self.session.get(url, params={"ts": timestamp})
            resp.raise_for_status()
            logger.info(
                "F95Checker Full Details Success",
                extra={"status_code": resp.status_code, "thread_id": thread_id},
            )
            return resp.json()
        except Exception as e:
            logger.error(
                f"F95Checker full details failed for {thread_id}",
                exc_info=True,
                extra={"url": url, "thread_id": thread_id, "error": str(e)},
            )
            return None
