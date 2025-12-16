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
        # In a real persistence scenario, we should track usage in DB or distinct file.
        # For this MVP/Task, we'll keep a simple in-memory counter or just respect
        # the user's wish to "configure" it (limit logic in orchestrator).

    def check_updates(self, thread_ids: List[int]) -> Dict[int, int]:
        """
        Bulk check for updates. Returns {thread_id: last_changed_timestamp}.
        """
        # API takes comma separated IDs
        ids_str = ",".join(map(str, thread_ids))
        url = f"{self.BASE_URL}/fast"

        try:
            resp = self.session.get(url, params={"ids": ids_str})
            resp.raise_for_status()
            # Response: {"123": 123456789, ...}
            return {int(k): v for k, v in resp.json().items()}
        except Exception as e:
            logger.error(f"F95Checker fast check failed: {e}")
            return {}

    def get_game_details(
        self, thread_id: int, timestamp: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get full details. Requires timestamp from fast check.
        """
        url = f"{self.BASE_URL}/full/{thread_id}"
        try:
            resp = self.session.get(url, params={"ts": timestamp})
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"F95Checker full details failed for {thread_id}: {e}")
            return None
