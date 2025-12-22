import requests
import logging
from typing import Optional, List, Dict, Any
from app.settings import settings

logger = logging.getLogger(__name__)


class F95ZoneClient:
    BASE_URL = "https://f95zone.to"
    LATEST_DATA_URL = f"{BASE_URL}/sam/latest_alpha/latest_data.php"
    LOGIN_URL = f"{BASE_URL}/login/login"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
        )
        self.username = settings.F95_USERNAME
        self.password = settings.F95_PASSWORD
        self._logged_in = False

    def login(self) -> bool:
        """
        Logs in to F95Zone to get session cookies.
        Note: This is a simplified login. Real login often requires handling CSRF tokens
        and potential 2FA/CAPTCHA. We will attempt standard login logic here.
        """
        # For the "Latest Updates" API, strictly speaking, just having valid cookies
        # (even if anonymous sometimes) might work for *reading* public lists,
        # but the request was to use credentials.

        # NOTE: If we want to implement full login logic (CSRF, etc) we should port
        # the legacy code's login mechanism. For now, I will assume basic session
        # or that the user might need to provide cookies if 2FA is on.
        # But let's try to implement the basic POST login.

        try:
            # 1. Get CSRF Token
            resp = self.session.get(self.LOGIN_URL)
            resp.raise_for_status()

            # Simple token extraction (regex or soup)
            # In legacy code it used soup.select_one('input[name="_xfToken"]')
            # I will use a simple split/regex to avoid soup overhead if possible,
            # but soup is installed so let's use it for reliability.
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(resp.text, "html.parser")
            token_input = soup.select_one('input[name="_xfToken"]')

            if not token_input:
                logger.error("Could not find login CSRF token.")
                return False

            xf_token = token_input.get("value")

            # 2. Post Creds
            payload = {
                "login": self.username,
                "password": self.password,
                "_xfToken": xf_token,
                "remember": "1",
                "_xfRedirect": self.BASE_URL + "/",
            }

            login_resp = self.session.post(self.LOGIN_URL, data=payload)
            login_resp.raise_for_status()

            # Check success (usually redirect or cookie presence)
            # Legacy code checked for user ID in span
            if "xf_user" in self.session.cookies:
                self._logged_in = True
                logger.info(f"Logged in as {self.username}")
                return True
            else:
                logger.warning(
                    "Login failed (no xf_user cookie). Check credentials or 2FA."
                )
                return False

        except Exception as e:
            logger.error(f"Login exception: {e}")
            return False

    def get_latest_updates(
        self, page: int = 1, rows: int = 60, sort: str = "date"
    ) -> List[Dict[str, Any]]:
        """
        Fetches the latest updates from the API.
        """
        if not self._logged_in:
            if not self.login():
                logger.warning("Proceeding without login (results might be limited).")

        params = {
            "cmd": "list",
            "cat": "games",
            "page": page,
            "rows": rows,
            "sort": sort,
        }

        logger.info(
            "Calling F95Zone Latest Updates",
            extra={"url": self.LATEST_DATA_URL, "page": page, "rows": rows},
        )

        try:
            resp = self.session.get(self.LATEST_DATA_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

            if data.get("status") == "ok":
                results = data.get("msg", {}).get("data", [])
                logger.info(
                    "F95Zone Updates Success",
                    extra={
                        "status_code": resp.status_code,
                        "result_count": len(results),
                    },
                )
                return results
            else:
                logger.error("API returned error status", extra={"response": data})
                return None
        except Exception as e:
            logger.error(
                "Failed to fetch updates", exc_info=True, extra={"error": str(e)}
            )
            return None

    def search_games(
        self, query: str, author: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Searches for a specific game.
        """
        if not self._logged_in:
            self.login()

        params = {
            "cmd": "list",
            "cat": "games",
            "search": query,
            "rows": 60,
            "sort": "date",
        }

        logger.info(
            "Calling F95Zone Search",
            extra={"url": self.LATEST_DATA_URL, "query": query},
        )

        try:
            resp = self.session.get(self.LATEST_DATA_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

            results = data.get("msg", {}).get("data", [])
            logger.info(
                "F95Zone Search Success",
                extra={
                    "status_code": resp.status_code,
                    "query": query,
                    "result_count": len(results),
                },
            )
            return results
        except Exception as e:
            logger.error(
                "Search failed", exc_info=True, extra={"query": query, "error": str(e)}
            )
            return []
