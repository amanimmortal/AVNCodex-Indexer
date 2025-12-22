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
        Automatically batches requests in groups of 10 to respect API limits.
        """
        results = {}
        chunk_size = 10
        url = f"{self.BASE_URL}/fast"

        for i in range(0, len(thread_ids), chunk_size):
            chunk = thread_ids[i : i + chunk_size]
            ids_str = ",".join(map(str, chunk))

            logger.info(
                f"Calling F95Checker Fast Check (Batch {i // chunk_size + 1})",
                extra={
                    "url": url,
                    "count": len(chunk),
                    "ids_preview": chunk,
                },
            )

            try:
                resp = self.session.get(url, params={"ids": ids_str})
                resp.raise_for_status()

                data = resp.json()

                # Merge results
                batch_results = {int(k): v for k, v in data.items()}
                results.update(batch_results)

                logger.info(
                    "F95Checker Fast Check Batch Success",
                    extra={
                        "status_code": resp.status_code,
                        "response_count": len(batch_results),
                    },
                )

            except Exception as e:
                logger.error(
                    "F95Checker fast check failed for batch",
                    exc_info=True,
                    extra={"url": url, "batch": chunk, "error": str(e)},
                )
                # Continue processing other batches even if one fails

        return results

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
